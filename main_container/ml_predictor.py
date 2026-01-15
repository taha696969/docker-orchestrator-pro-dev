import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.utils.validation import check_is_fitted
import joblib
import os
from datetime import datetime


class MLPredictor:
    def __init__(self, model_path='models/predictor_model.pkl'):
        self.model_path = model_path
        self.scaler = StandardScaler()
        self.flux_scaler = StandardScaler()
        self.cpu_model = None
        self.memory_model = None
        self.flux_model = None
        self.load_threshold = 80
        self.min_train_points = int(os.getenv('ML_MIN_TRAIN_POINTS', '30'))
        self.min_flux_train_points = int(os.getenv('FLUX_MIN_TRAIN_POINTS', '8'))
        self.flux_scale_threshold_rps = float(os.getenv('FLUX_SCALE_THRESHOLD_RPS', '5'))
        
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
                try:
                    self.flux_model = models.get('flux_model')
                except Exception:
                    self.flux_model = None
                try:
                    self.flux_scaler = models.get('flux_scaler') or StandardScaler()
                except Exception:
                    self.flux_scaler = StandardScaler()
                print("✅ Modèles ML chargés")
            else:
                print("⚠️ Aucun modèle pré-entraîné trouvé, utilisation de modèles par défaut")
                self.cpu_model = RandomForestRegressor(n_estimators=100, random_state=42)
                self.memory_model = RandomForestRegressor(n_estimators=100, random_state=42)
                self.flux_model = RandomForestRegressor(n_estimators=100, random_state=42)
        except Exception as e:
            print(f"Erreur chargement modèles: {e}")
            self.cpu_model = RandomForestRegressor(n_estimators=100, random_state=42)
            self.memory_model = RandomForestRegressor(n_estimators=100, random_state=42)
            self.flux_model = RandomForestRegressor(n_estimators=100, random_state=42)
    
    def save_models(self):
        """Sauvegarder les modèles entraînés"""
        try:
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            models = {
                'cpu_model': self.cpu_model,
                'memory_model': self.memory_model,
                'scaler': self.scaler,
                'flux_model': self.flux_model,
                'flux_scaler': self.flux_scaler
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

    def prepare_flux_features(self, flux_values):
        if flux_values is None:
            return None
        if len(flux_values) < 5:
            return None

        v = list(flux_values)
        w = v[-10:]

        flux_mean = np.mean(w)
        flux_std = np.std(w)
        flux_max = np.max(w)
        flux_trend = self._calculate_trend(w)

        features = [flux_mean, flux_std, flux_max, flux_trend]
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
    
    def _models_ready(self):
        try:
            if self.cpu_model is None or self.memory_model is None or self.scaler is None:
                return False
            check_is_fitted(self.scaler)
            check_is_fitted(self.cpu_model)
            check_is_fitted(self.memory_model)
            return True
        except Exception:
            return False

    def _flux_model_ready(self):
        try:
            if self.flux_model is None or self.flux_scaler is None:
                return False
            check_is_fitted(self.flux_scaler)
            check_is_fitted(self.flux_model)
            return True
        except Exception:
            return False

    def _autotrain_from_series(self, cpu_values, memory_values, horizon=5):
        try:
            if cpu_values is None or memory_values is None:
                return False
            if len(cpu_values) < self.min_train_points or len(memory_values) < self.min_train_points:
                return False
            historical_data = []
            for i in range(min(len(cpu_values), len(memory_values))):
                historical_data.append({
                    'timestamp': datetime.now(),
                    'cpu_percent': float(cpu_values[i]),
                    'memory_percent': float(memory_values[i])
                })
            return bool(self.train_model(historical_data))
        except Exception:
            return False

    def _autotrain_flux_from_series(self, flux_values, horizon=1):
        try:
            if flux_values is None:
                return False
            min_needed = max(int(self.min_flux_train_points or 0), 7)
            if len(flux_values) < min_needed:
                return False
            historical_data = []
            for i in range(len(flux_values)):
                historical_data.append({
                    'timestamp': datetime.now(),
                    'flux_rps': float(flux_values[i])
                })
            return bool(self.train_model(historical_data, flux_horizon=horizon))
        except Exception:
            return False
    
    def predict_load(self, cpu_values, memory_values, horizon=5, flux_values=None, flux_horizon=1):
        """Prédire la charge future et décider si scaling nécessaire"""
        try:
            if cpu_values is None or memory_values is None:
                return {
                    'predicted_cpu': 0,
                    'predicted_memory': 0,
                    'predicted_flux_rps': None,
                    'cpu_trend': 0,
                    'memory_trend': 0,
                    'should_scale': False,
                    'reasons': ['Données manquantes'],
                    'confidence': 0
                }

            cpu_values = list(cpu_values)
            memory_values = list(memory_values)

            flux_pred = None
            flux_fallback = False
            if flux_values is not None:
                flux_values = list(flux_values)
                if not self._flux_model_ready():
                    self._autotrain_flux_from_series(flux_values, horizon=flux_horizon)
                flux_features = self.prepare_flux_features(flux_values)
                if flux_features is not None and self._flux_model_ready():
                    Xf = self.flux_scaler.transform(flux_features)
                    flux_pred = float(self.flux_model.predict(Xf)[0])
                    flux_pred = max(0.0, float(flux_pred))
                if flux_pred is None:
                    try:
                        flux_pred = float(np.mean(flux_values[-5:]))
                        flux_pred = max(0.0, float(flux_pred))
                        flux_fallback = True
                    except Exception:
                        flux_pred = None

            if not self._models_ready():
                self._autotrain_from_series(cpu_values, memory_values, horizon=horizon)

            features = self.prepare_features(cpu_values, memory_values)
            if features is None:
                return {
                    'predicted_cpu': 0,
                    'predicted_memory': 0,
                    'predicted_flux_rps': flux_pred,
                    'cpu_trend': 0,
                    'memory_trend': 0,
                    'should_scale': False,
                    'reasons': ['Pas assez de données'],
                    'confidence': self._calculate_confidence(cpu_values, memory_values)
                }

            if self._models_ready():
                X = self.scaler.transform(features)
                predicted_cpu = float(self.cpu_model.predict(X)[0])
                predicted_memory = float(self.memory_model.predict(X)[0])

                predicted_cpu = max(0.0, min(predicted_cpu, 100.0))
                predicted_memory = max(0.0, min(predicted_memory, 100.0))

                should_scale = False
                reasons = []
                if flux_values is not None:
                    if flux_pred is not None and float(flux_pred) >= float(self.flux_scale_threshold_rps):
                        should_scale = True
                        reasons.append(f"Flux prédit dépasse {self.flux_scale_threshold_rps} rps")
                    elif flux_fallback and flux_pred is not None:
                        reasons.append("Modèle flux non entraîné: utilisation du flux actuel")
                else:
                    if predicted_cpu > self.load_threshold:
                        should_scale = True
                        reasons.append(f"CPU prédit dépasse {self.load_threshold}%")
                    if predicted_memory > self.load_threshold:
                        should_scale = True
                        reasons.append(f"Mémoire prédite dépasse {self.load_threshold}%")

                return {
                    'predicted_cpu': predicted_cpu,
                    'predicted_memory': predicted_memory,
                    'predicted_flux_rps': flux_pred,
                    'cpu_trend': 0,
                    'memory_trend': 0,
                    'should_scale': should_scale,
                    'reasons': reasons,
                    'confidence': self._calculate_confidence(cpu_values, memory_values)
                }

            return {
                'predicted_cpu': None,
                'predicted_memory': None,
                'predicted_flux_rps': flux_pred,
                'cpu_trend': 0,
                'memory_trend': 0,
                'should_scale': bool(
                    (flux_values is not None and flux_pred is not None and float(flux_pred) >= float(self.flux_scale_threshold_rps))
                    or
                    (flux_values is None and (float(np.mean(cpu_values[-5:])) > float(self.load_threshold) or float(np.mean(memory_values[-5:])) > float(self.load_threshold)))
                ),
                'reasons': (
                    ([f"Flux prédit dépasse {self.flux_scale_threshold_rps} rps"] if (flux_values is not None and flux_pred is not None and float(flux_pred) >= float(self.flux_scale_threshold_rps)) else [])
                    or
                    (["Modèle flux non entraîné: utilisation du flux actuel"] if (flux_values is not None and flux_fallback) else [])
                    or
                    (["CPU/Mémoire actuels dépassent le seuil"] if (flux_values is None and (float(np.mean(cpu_values[-5:])) > float(self.load_threshold) or float(np.mean(memory_values[-5:])) > float(self.load_threshold))) else ['Modèle ML non entraîné'])
                ),
                'confidence': self._calculate_confidence(cpu_values, memory_values)
            }
            
        except Exception as e:
            print(f"Erreur prédiction: {e}")
            return {
                'predicted_cpu': 0,
                'predicted_memory': 0,
                'predicted_flux_rps': None,
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
    
    def train_model(self, historical_data, flux_horizon=1):
        """Entraîner les modèles avec des données historiques"""
        try:
            if not historical_data or len(historical_data) < self.min_train_points:
                print(f"⚠️ Pas assez de données pour l'entraînement (minimum {self.min_train_points} points)")
                ok = False
            else:
                ok = True
            
            X_train = []
            y_cpu_train = []
            y_memory_train = []

            X_flux_train = []
            y_flux_train = []
            
            if ok:
                for i in range(10, len(historical_data) - 5):
                    cpu_window = [d.get('cpu_percent', 0) for d in historical_data[i-10:i]]
                    memory_window = [d.get('memory_percent', 0) for d in historical_data[i-10:i]]

                    features = self.prepare_features(cpu_window, memory_window)
                    if features is not None:
                        X_train.append(features[0])
                        y_cpu_train.append(float(historical_data[i+5].get('cpu_percent', 0) or 0))
                        y_memory_train.append(float(historical_data[i+5].get('memory_percent', 0) or 0))

            flux_docs = []
            try:
                for d in historical_data:
                    if isinstance(d, dict) and ('flux_rps' in d):
                        flux_docs.append(d)
            except Exception:
                flux_docs = []

            min_flux_needed = max(int(self.min_flux_train_points or 0), 7)
            has_flux = bool(len(flux_docs) >= int(min_flux_needed))

            if has_flux:
                horizon = int(flux_horizon or 1)
                if horizon < 1:
                    horizon = 1

                for i in range(5, len(flux_docs) - horizon):
                    flux_window = [d.get('flux_rps', 0) for d in flux_docs[i-5:i]]
                    f = self.prepare_flux_features(flux_window)
                    if f is not None:
                        X_flux_train.append(f[0])
                        y_flux_train.append(float(flux_docs[i + horizon].get('flux_rps', 0) or 0))
            
            trained_any = False

            if ok:
                if len(X_train) < 10:
                    print("⚠️ Pas assez de features extraites pour l'entraînement")
                else:
                    X_train = np.array(X_train)
                    y_cpu_train = np.array(y_cpu_train)
                    y_memory_train = np.array(y_memory_train)

                    X_train_scaled = self.scaler.fit_transform(X_train)

                    print("🎓 Entraînement du modèle CPU...")
                    self.cpu_model.fit(X_train_scaled, y_cpu_train)

                    print("🎓 Entraînement du modèle mémoire...")
                    self.memory_model.fit(X_train_scaled, y_memory_train)

                    trained_any = True
            
            if has_flux:
                if len(X_flux_train) < 1:
                    print("⚠️ Pas assez de features flux extraites pour l'entraînement")
                else:
                    X_flux_train = np.array(X_flux_train)
                    y_flux_train = np.array(y_flux_train)

                    X_flux_scaled = self.flux_scaler.fit_transform(X_flux_train)
                    if self.flux_model is None:
                        self.flux_model = RandomForestRegressor(n_estimators=100, random_state=42)

                    print("🎓 Entraînement du modèle flux...")
                    self.flux_model.fit(X_flux_scaled, y_flux_train)
                    trained_any = True
            
            if trained_any:
                self.save_models()

            try:
                if ok:
                    print(f"✅ Entraînement terminé avec {len(X_train)} échantillons")
                elif has_flux:
                    print(f"✅ Entraînement flux terminé avec {len(X_flux_train)} échantillons")
            except Exception:
                pass

            return bool(trained_any)
            
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
                try:
                    pred = result.get('predicted_cpu')
                    if pred is None:
                        continue
                    predictions.append(float(pred))
                    actuals.append(float(test_data[i+5]['cpu_percent']))
                except Exception:
                    continue

            if not predictions:
                return None
            
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