"""
Exemples d'utilisation avancée du système d'orchestration
"""

import requests
import time
import json
from datetime import datetime

# Configuration
ORCHESTRATOR_URL = "http://localhost:5000"

# ============================================
# Exemple 1: Configuration d'une Architecture Web Classique
# ============================================

def setup_web_architecture():
    """
    Créer une architecture web complète avec:
    - 2 serveurs web (Nginx)
    - 1 serveur d'application (Python)
    - 1 base de données (PostgreSQL)
    """
    print("🏗️  Configuration d'une architecture web...")
    
    # Créer les conteneurs
    containers = [
        {
            "name": "nginx_1",
            "image": "nginx:alpine",
            "ports": {"80": "8080"}
        },
        {
            "name": "nginx_2",
            "image": "nginx:alpine",
            "ports": {"80": "8081"}
        },
        {
            "name": "app_server",
            "image": "python:3.9-slim",
            "env": {"APP_ENV": "production"}
        },
        {
            "name": "postgres_db",
            "image": "postgres:14",
            "env": {
                "POSTGRES_PASSWORD": "secret",
                "POSTGRES_DB": "app_db"
            }
        }
    ]
    
    # Créer tous les conteneurs
    for container in containers:
        response = requests.post(
            f"{ORCHESTRATOR_URL}/container/create",
            json=container
        )
        print(f"✅ Conteneur créé: {container['name']}")
        time.sleep(2)
    
    # Définir les relations
    relations = [
        {"from": "nginx_1", "to": "app_server", "type": "depends_on"},
        {"from": "nginx_2", "to": "app_server", "type": "depends_on"},
        {"from": "app_server", "to": "postgres_db", "type": "uses"}
    ]
    
    for relation in relations:
        response = requests.post(
            f"{ORCHESTRATOR_URL}/relation/add",
            json=relation
        )
        print(f"🔗 Relation ajoutée: {relation['from']} -> {relation['to']}")
    
    print("✅ Architecture web configurée!")


# ============================================
# Exemple 2: Test de Charge et Monitoring
# ============================================

def load_test_with_monitoring(container_name, duration=60, requests_per_second=10):
    """
    Effectuer un test de charge tout en monitorant les métriques
    """
    print(f"🚀 Test de charge sur {container_name}...")
    print(f"   Durée: {duration}s, RPS: {requests_per_second}")
    
    start_time = time.time()
    request_count = 0
    metrics_history = []
    
    while time.time() - start_time < duration:
        # Envoyer des requêtes
        for _ in range(requests_per_second):
            try:
                # Simuler une requête au conteneur
                # (adapter selon votre endpoint)
                request_count += 1
            except:
                pass
        
        # Récupérer les métriques toutes les 5 secondes
        if request_count % (requests_per_second * 5) == 0:
            try:
                response = requests.get(
                    f"{ORCHESTRATOR_URL}/container/{container_name}/metrics"
                )
                metrics = response.json()
                if metrics:
                    latest = metrics[-1]
                    metrics_history.append(latest)
                    
                    print(f"⏱️  {time.time() - start_time:.1f}s - "
                          f"CPU: {latest['cpu_percent']:.1f}%, "
                          f"MEM: {latest['memory_percent']:.1f}%")
            except:
                pass
        
        time.sleep(1 / requests_per_second)
    
    print(f"\n✅ Test terminé!")
    print(f"   Total requêtes: {request_count}")
    
    # Analyser les résultats
    if metrics_history:
        avg_cpu = sum(m['cpu_percent'] for m in metrics_history) / len(metrics_history)
        max_cpu = max(m['cpu_percent'] for m in metrics_history)
        avg_mem = sum(m['memory_percent'] for m in metrics_history) / len(metrics_history)
        
        print(f"\n📊 Résultats:")
        print(f"   CPU moyen: {avg_cpu:.2f}%")
        print(f"   CPU max: {max_cpu:.2f}%")
        print(f"   Mémoire moyenne: {avg_mem:.2f}%")


# ============================================
# Exemple 3: Surveillance du Scaling Automatique
# ============================================

def monitor_autoscaling(container_name, check_interval=10, max_duration=300):
    """
    Surveiller le scaling automatique d'un conteneur
    """
    print(f"👁️  Surveillance du scaling pour {container_name}...")
    
    start_time = time.time()
    scaling_events = []
    previous_replicas = 0
    
    while time.time() - start_time < max_duration:
        try:
            # Vérifier le nombre de répliques
            response = requests.get(f"{ORCHESTRATOR_URL}/containers/list")
            containers = response.json()['containers']
            
            # Compter les répliques
            replicas = [c for c in containers if c.startswith(container_name)]
            current_replicas = len(replicas)
            
            # Détecter un événement de scaling
            if current_replicas != previous_replicas:
                event = {
                    'timestamp': datetime.now().isoformat(),
                    'container': container_name,
                    'previous_count': previous_replicas,
                    'new_count': current_replicas,
                    'action': 'scale_up' if current_replicas > previous_replicas else 'scale_down'
                }
                scaling_events.append(event)
                
                print(f"\n🔄 SCALING DÉTECTÉ!")
                print(f"   Conteneur: {container_name}")
                print(f"   {previous_replicas} -> {current_replicas} répliques")
                print(f"   Action: {event['action']}")
                
                previous_replicas = current_replicas
            
            # Afficher l'état actuel
            response = requests.get(
                f"{ORCHESTRATOR_URL}/container/{container_name}/metrics"
            )
            if response.ok:
                metrics = response.json()
                if metrics:
                    latest = metrics[-1]
                    print(f"   CPU: {latest['cpu_percent']:.1f}%, "
                          f"MEM: {latest['memory_percent']:.1f}%, "
                          f"Répliques: {current_replicas}")
        
        except Exception as e:
            print(f"❌ Erreur: {e}")
        
        time.sleep(check_interval)
    
    # Rapport final
    print(f"\n📋 Rapport de Scaling:")
    print(f"   Événements détectés: {len(scaling_events)}")
    for event in scaling_events:
        print(f"   - {event['timestamp']}: {event['action']} "
              f"({event['previous_count']} -> {event['new_count']})")


# ============================================
# Exemple 4: Simulation de Pic de Charge
# ============================================

def simulate_traffic_spike(container_name, spike_duration=30):
    """
    Simuler un pic de trafic soudain pour tester le scaling
    """
    print(f"⚡ Simulation d'un pic de charge sur {container_name}...")
    
    # Phase 1: Charge normale (30 req/s)
    print("\n📊 Phase 1: Charge normale (30 req/s)...")
    for i in range(10):
        print(f"   Envoi de requêtes... {i+1}/10")
        time.sleep(1)
    
    # Phase 2: PIC de charge (200 req/s)
    print(f"\n🚀 Phase 2: PIC DE CHARGE (200 req/s pendant {spike_duration}s)!")
    for i in range(spike_duration):
        print(f"   ⚡ PIC EN COURS... {i+1}/{spike_duration}")
        time.sleep(1)
    
    # Phase 3: Retour à la normale
    print("\n📉 Phase 3: Retour à la normale...")
    for i in range(10):
        print(f"   Charge réduite... {i+1}/10")
        time.sleep(1)
    
    # Vérifier les événements de scaling
    try:
        response = requests.get(f"{ORCHESTRATOR_URL}/scaling/history")
        if response.ok:
            history = response.json()
            recent_events = [e for e in history 
                           if e['container_name'] == container_name]
            
            print(f"\n📊 Résultats:")
            print(f"   Événements de scaling: {len(recent_events)}")
            for event in recent_events[-5:]:  # 5 derniers
                print(f"   - {event['event_type']}: "
                      f"CPU prédit {event.get('predicted_cpu', 'N/A')}%")
    except:
        pass


# ============================================
# Exemple 5: Analyse des Performances ML
# ============================================

def analyze_ml_performance():
    """
    Analyser les performances du modèle de Machine Learning
    """
    print("🤖 Analyse des performances du modèle ML...")
    
    try:
        response = requests.get(f"{ORCHESTRATOR_URL}/predictions/accuracy")
        if response.ok:
            data = response.json()
            
            print(f"\n📊 Rapport de Performance ML:")
            print(f"   Nombre de prédictions: {data.get('count', 0)}")
            print(f"   Précision moyenne: {data.get('accuracy', 0):.2f}%")
            print(f"   Erreur moyenne: {data.get('mean_error', 0):.2f}%")
            
            # Analyser les prédictions récentes
            predictions = data.get('predictions', [])
            if predictions:
                print(f"\n🔍 Dernières prédictions:")
                for pred in predictions[-5:]:
                    print(f"   - Conteneur: {pred['container_name']}")
                    print(f"     Prédit: {pred['predicted_cpu']:.1f}%, "
                          f"Réel: {pred.get('actual_cpu', 'N/A')}")
                    print(f"     Scaling déclenché: {pred.get('should_scale', False)}")
        else:
            print("❌ Impossible de récupérer les données")
    
    except Exception as e:
        print(f"❌ Erreur: {e}")


# ============================================
# Exemple 6: Visualisation du Graphe
# ============================================

def visualize_dependencies():
    """
    Obtenir et afficher les dépendances entre conteneurs
    """
    print("🌐 Visualisation du graphe de dépendances...")
    
    try:
        response = requests.get(f"{ORCHESTRATOR_URL}/relations/graph")
        if response.ok:
            graph_data = response.json()
            
            print(f"\n📊 Statistiques du Graphe:")
            print(f"   Conteneurs: {graph_data.get('total_containers', 0)}")
            print(f"   Relations: {graph_data.get('total_relations', 0)}")
            print(f"   Conteneurs isolés: {graph_data.get('isolated_containers', 0)}")
            print(f"   Cycles détectés: {graph_data.get('cycles', 0)}")
            
            # Afficher les conteneurs critiques
            critical = graph_data.get('most_critical', [])
            if critical:
                print(f"\n⚠️  Conteneurs critiques (plus de dépendants):")
                for container in critical:
                    print(f"   - {container}")
        else:
            print("❌ Impossible de récupérer le graphe")
    
    except Exception as e:
        print(f"❌ Erreur: {e}")


# ============================================
# Menu Principal
# ============================================

def main():
    print("=" * 60)
    print("🐳 EXEMPLES D'UTILISATION - ORCHESTRATEUR DOCKER")
    print("=" * 60)
    print("\nChoisissez un exemple:")
    print("1. Configuration d'une architecture web")
    print("2. Test de charge avec monitoring")
    print("3. Surveillance du scaling automatique")
    print("4. Simulation de pic de charge")
    print("5. Analyse des performances ML")
    print("6. Visualisation du graphe de dépendances")
    print("0. Quitter")
    
    choice = input("\nVotre choix: ")
    
    if choice == "1":
        setup_web_architecture()
    elif choice == "2":
        container = input("Nom du conteneur: ")
        load_test_with_monitoring(container)
    elif choice == "3":
        container = input("Nom du conteneur: ")
        monitor_autoscaling(container)
    elif choice == "4":
        container = input("Nom du conteneur: ")
        simulate_traffic_spike(container)
    elif choice == "5":
        analyze_ml_performance()
    elif choice == "6":
        visualize_dependencies()
    elif choice == "0":
        print("Au revoir!")
        return
    else:
        print("❌ Choix invalide")


if __name__ == "__main__":
    main()