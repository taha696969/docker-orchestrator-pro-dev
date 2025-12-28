import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
import joblib
import os
from datetime import datetime


class MLPredictor:
    def __init__(self, model_path='models/predictor_model.pkl'):
        self.model_path = model_path
        self.scaler = StandardScaler()
        self.cpu_model = None
        self.memory_model = None
        self.load_threshold = 80
        
        # Charger les modèles s'ils existent
        self.load_models()
    
    def load_models(self):
        """Charger les modèles pré-entraînés"""
        try:
            if os.path.exists(self.model_path):
                models = joblib.load(self.model_path)
                self.cpu_model = models['cpu_model']
                self.memory_model = models['memory_model']
                self.scaler = models['scaler']
                print("✅ Modèles ML chargés")
            else:
                print("⚠️ Aucun modèle pré-entraîné trouvé, utilisation de modèles par défaut")
                self.cpu_model = RandomForestRegressor(n_estimators=100, random_state=42)
                self.memory_model = RandomForestRegressor(n_estimators=100, random_state=42)
        except Exception as e:
            print(f"Erreur chargement modèles: {e}")
            self.cpu_model = RandomForestRegressor(n_estimators=100, random_state=42)
            self.memory_model = RandomForestRegressor(n_estimators=100, random_state=42)
    
    def save_models(self):
        """Sauvegarder les modèles entraînés"""
        try:
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            models = {
                'cpu_model': self.cpu_model,
                'memory_model': self.memory_model,
                'scaler': self.scaler
            }
            joblib.dump(models, self.model_path)
            print(f"✅ Modèles sauvegardés: {self.model_path}")
            return True
        except Exception as e:
            print(f"Erreur sauvegarde modèles: {e}")
            return False
    
    def prepare_features(self, cpu_values, memory_values):
        """Préparer les features pour la prédiction"""
        if len(cpu_values) < 5 or len(memory_values) < 5:
            return None
        
        features = []
        
        # Statistiques de base
        cpu_mean = np.mean(cpu_values[-10:])
        cpu_std = np.std(cpu_values[-10:])
        cpu_max = np.max(cpu_values[-10:])
        cpu_trend = self._calculate_trend(cpu_values[-10:])
        
        memory_mean = np.mean(memory_values[-10:])
        memory_std = np.std(memory_values[-10:])
        memory_max = np.max(memory_values[-10:])
        memory_trend = self._calculate_trend(memory_values[-10:])
        
        features = [
            cpu_mean, cpu_std, cpu_max, cpu_trend,
            memory_mean, memory_std, memory_max, memory_trend
        ]
        
        return np.array(features).reshape(1, -1)
    
    def _calculate_trend(self, values):
        """Calculer la tendance (pente) d'une série de valeurs"""
        if len(values) < 2:
            return 0.0
        
        x = np.arange(len(values)).reshape(-1, 1)
        y = np.array(values)
        
        try:
            model = LinearRegression()
            model.fit(x, y)
            return model.coef_[0]
        except:
            return 0.0
    
    def predict_load(self, cpu_values, memory_values, horizon=5):
        """Prédire la charge future et décider si scaling nécessaire"""
        try:
            # Prédiction simple basée sur la tendance
            cpu_trend = self._calculate_trend(cpu_values[-20:])
            memory_trend = self._calculate_trend(memory_values[-20:])
            
            current_cpu = cpu_values[-1] if cpu_values else 0
            current_memory = memory_values[-1] if memory_values else 0
            
            # Prédiction linéaire simple
            predicted_cpu = current_cpu + (cpu_trend * horizon)
            predicted_memory = current_memory + (memory_trend * horizon)
            
            # Calcul de la volatilité
            cpu_volatility = np.std(cpu_values[-10:]) if len(cpu_values) >= 10 else 0
            memory_volatility = np.std(memory_values[-10:]) if len(memory_values) >= 10 else 0
            
            # Décision de scaling
            should_scale = False
            reasons = []
            
            # Critères de scaling
            if predicted_cpu > self.load_threshold:
                should_scale = True
                reasons.append(f"CPU prédit dépasse {self.load_threshold}%")
            
            if predicted_memory > self.load_threshold:
                should_scale = True
                reasons.append(f"Mémoire prédite dépasse {self.load_threshold}%")
            
            if cpu_trend > 5 and current_cpu > 60:
                should_scale = True
                reasons.append("Tendance CPU fortement croissante")
            
            if memory_trend > 5 and current_memory > 60:
                should_scale = True
                reasons.append("Tendance mémoire fortement croissante")
            
            # Vérifier les pics soudains
            if cpu_volatility > 20:
                should_scale = True
                reasons.append("Forte volatilité CPU détectée")
            
            result = {
                'predicted_cpu': min(predicted_cpu, 100),
                'predicted_memory': min(predicted_memory, 100),
                'cpu_trend': cpu_trend,
                'memory_trend': memory_trend,
                'cpu_volatility': cpu_volatility,
                'memory_volatility': memory_volatility,
                'should_scale': should_scale,
                'reasons': reasons,
                'confidence': self._calculate_confidence(cpu_values, memory_values)
            }
            
            return result
            
        except Exception as e:
            print(f"Erreur prédiction: {e}")
            return {
                'predicted_cpu': 0,
                'predicted_memory': 0,
                'cpu_trend': 0,
                'memory_trend': 0,
                'should_scale': False,
                'reasons': ['Erreur de prédiction'],
                'confidence': 0
            }
    
    def _calculate_confidence(self, cpu_values, memory_values):
        """Calculer le niveau de confiance de la prédiction"""
        # Plus on a de données, plus on est confiant
        data_points = min(len(cpu_values), len(memory_values))
        
        if data_points < 10:
            return 0.3
        elif data_points < 20:
            return 0.5
        elif data_points < 50:
            return 0.7
        else:
            return 0.9
    
    def train_model(self, historical_data):
        """Entraîner les modèles avec des données historiques"""
        try:
            if not historical_data or len(historical_data) < 50:
                print("⚠️ Pas assez de données pour l'entraînement (minimum 50 points)")
                return False
            
            # Préparer les données d'entraînement
            X_train = []
            y_cpu_train = []
            y_memory_train = []
            
            for i in range(10, len(historical_data) - 5):
                cpu_window = [d['cpu_percent'] for d in historical_data[i-10:i]]
                memory_window = [d['memory_percent'] for d in historical_data[i-10:i]]
                
                features = self.prepare_features(cpu_window, memory_window)
                if features is not None:
                    X_train.append(features[0])
                    y_cpu_train.append(historical_data[i+5]['cpu_percent'])
                    y_memory_train.append(historical_data[i+5]['memory_percent'])
            
            if len(X_train) < 20:
                print("⚠️ Pas assez de features extraites pour l'entraînement")
                return False
            
            X_train = np.array(X_train)
            y_cpu_train = np.array(y_cpu_train)
            y_memory_train = np.array(y_memory_train)
            
            # Normaliser les features
            X_train_scaled = self.scaler.fit_transform(X_train)
            
            # Entraîner les modèles
            print("🎓 Entraînement du modèle CPU...")
            self.cpu_model.fit(X_train_scaled, y_cpu_train)
            
            print("🎓 Entraînement du modèle mémoire...")
            self.memory_model.fit(X_train_scaled, y_memory_train)
            
            # Sauvegarder les modèles
            self.save_models()
            
            print(f"✅ Entraînement terminé avec {len(X_train)} échantillons")
            return True
            
        except Exception as e:
            print(f"Erreur entraînement: {e}")
            return False
    
    def evaluate_model(self, test_data):
        """Évaluer la performance des modèles"""
        try:
            if not test_data or len(test_data) < 20:
                return None
            
            predictions = []
            actuals = []
            
            for i in range(10, len(test_data) - 5):
                cpu_window = [d['cpu_percent'] for d in test_data[i-10:i]]
                memory_window = [d['memory_percent'] for d in test_data[i-10:i]]
                
                result = self.predict_load(cpu_window, memory_window, horizon=5)
                predictions.append(result['predicted_cpu'])
                actuals.append(test_data[i+5]['cpu_percent'])
            
            # Calculer l'erreur
            mae = np.mean(np.abs(np.array(predictions) - np.array(actuals)))
            rmse = np.sqrt(np.mean((np.array(predictions) - np.array(actuals))**2))
            
            return {
                'mae': mae,
                'rmse': rmse,
                'accuracy': max(0, 100 - mae)
            }
            
        except Exception as e:
            print(f"Erreur évaluation: {e}")
            return None
    
    def detect_anomaly(self, cpu_values, memory_values):
        """Détecter les anomalies dans les métriques"""
        anomalies = []
        
        if len(cpu_values) < 10:
            return anomalies
        
        # Calcul de la moyenne et écart-type
        cpu_mean = np.mean(cpu_values)
        cpu_std = np.std(cpu_values)
        memory_mean = np.mean(memory_values)
        memory_std = np.std(memory_values)
        
        # Détecter les valeurs aberrantes (> 3 écarts-types)
        current_cpu = cpu_values[-1]
        current_memory = memory_values[-1]
        
        if abs(current_cpu - cpu_mean) > 3 * cpu_std:
            anomalies.append({
                'type': 'cpu_spike',
                'value': current_cpu,
                'expected': cpu_mean,
                'severity': 'high'
            })
        
        if abs(current_memory - memory_mean) > 3 * memory_std:
            anomalies.append({
                'type': 'memory_spike',
                'value': current_memory,
                'expected': memory_mean,
                'severity': 'high'
            })
        
        # Détecter les chutes brutales
        if len(cpu_values) >= 2:
            cpu_drop = cpu_values[-2] - current_cpu
            if cpu_drop > 40:
                anomalies.append({
                    'type': 'cpu_drop',
                    'drop': cpu_drop,
                    'severity': 'medium'
                })
        
        return anomalies