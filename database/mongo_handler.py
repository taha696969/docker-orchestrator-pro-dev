from pymongo import MongoClient
from datetime import datetime, timedelta
import os


class MongoHandler:
    def __init__(self):
        mongo_url = os.getenv('MONGO_URL', 'mongodb://mongodb:27017/')
        self.client = MongoClient(mongo_url)
        self.db = self.client['orchestrator_db']
        
        # Collections
        self.containers = self.db['containers']
        self.metrics = self.db['metrics']
        self.relations = self.db['relations']
        self.scaling_events = self.db['scaling_events']
        
        # Créer les index pour optimiser les requêtes
        self._create_indexes()
    
    def _create_indexes(self):
        """Créer les index MongoDB pour améliorer les performances"""
        try:
            self.metrics.create_index([('container_name', 1), ('timestamp', -1)])
            self.containers.create_index('name', unique=True)
            self.relations.create_index([('from_container', 1), ('to_container', 1)])
            self.scaling_events.create_index([('container_name', 1), ('timestamp', -1)])
        except Exception as e:
            print(f"Erreur création index: {e}")
    
    def insert_container_info(self, container_data):
        """Enregistrer les informations d'un conteneur"""
        try:
            container_data['created_at'] = datetime.now()
            self.containers.insert_one(container_data)
            return True
        except Exception as e:
            print(f"Erreur insertion conteneur: {e}")
            return False
    
    def insert_metrics(self, container_name, metrics):
        """Enregistrer les métriques d'un conteneur"""
        try:
            metrics_data = {
                'container_name': container_name,
                'timestamp': datetime.now(),
                'cpu_percent': metrics.get('cpu_percent', 0),
                'memory_percent': metrics.get('memory_percent', 0),
                'memory_usage': metrics.get('memory_usage', 0),
                'memory_limit': metrics.get('memory_limit', 0),
                'network_rx': metrics.get('network_rx', 0),
                'network_tx': metrics.get('network_tx', 0),
                'block_read': metrics.get('block_read', 0),
                'block_write': metrics.get('block_write', 0)
            }
            self.metrics.insert_one(metrics_data)
            return True
        except Exception as e:
            print(f"Erreur insertion métriques: {e}")
            return False
    
    def get_container_metrics(self, container_name, limit=100):
        """Récupérer l'historique des métriques d'un conteneur"""
        try:
            cursor = self.metrics.find(
                {'container_name': container_name}
            ).sort('timestamp', -1).limit(limit)
            return list(cursor)
        except Exception as e:
            print(f"Erreur récupération métriques: {e}")
            return []
    
    def get_metrics_range(self, container_name, start_time, end_time):
        """Récupérer les métriques dans un intervalle de temps"""
        try:
            cursor = self.metrics.find({
                'container_name': container_name,
                'timestamp': {
                    '$gte': start_time,
                    '$lte': end_time
                }
            }).sort('timestamp', 1)
            return list(cursor)
        except Exception as e:
            print(f"Erreur récupération métriques par plage: {e}")
            return []
    
    def insert_relation(self, from_container, to_container, relation_type='depends_on'):
        """Enregistrer une relation entre conteneurs"""
        try:
            relation_data = {
                'from_container': from_container,
                'to_container': to_container,
                'relation_type': relation_type,
                'created_at': datetime.now()
            }
            self.relations.update_one(
                {
                    'from_container': from_container,
                    'to_container': to_container,
                    'relation_type': relation_type
                },
                {'$setOnInsert': relation_data},
                upsert=True
            )
            return True
        except Exception as e:
            print(f"Erreur insertion relation: {e}")
            return False

    def remove_relation(self, from_container, to_container, relation_type=None):
        try:
            query = {
                'from_container': from_container,
                'to_container': to_container
            }
            if relation_type:
                query['relation_type'] = relation_type

            result = self.relations.delete_many(query)
            return int(getattr(result, 'deleted_count', 0))
        except Exception as e:
            print(f"Erreur suppression relation: {e}")
            return 0
    
    def remove_relations_for_container(self, container_name):
        try:
            query = {
                '$or': [
                    {'from_container': container_name},
                    {'to_container': container_name}
                ]
            }
            result = self.relations.delete_many(query)
            return int(getattr(result, 'deleted_count', 0))
        except Exception as e:
            print(f"Erreur suppression relations conteneur: {e}")
            return 0
    
    def get_container_relations(self, container_name):
        """Récupérer toutes les relations d'un conteneur"""
        try:
            # Relations sortantes
            outgoing = list(self.relations.find({'from_container': container_name}))
            # Relations entrantes
            incoming = list(self.relations.find({'to_container': container_name}))
            return {
                'outgoing': outgoing,
                'incoming': incoming
            }
        except Exception as e:
            print(f"Erreur récupération relations: {e}")
            return {'outgoing': [], 'incoming': []}
    
    def log_scaling_event(self, container_name, event_type, details):
        """Enregistrer un événement de scaling"""
        try:
            event_data = {
                'container_name': container_name,
                'event_type': event_type,  # 'scale_up', 'scale_down', 'replica_created'
                'details': details,
                'timestamp': datetime.now()
            }
            self.scaling_events.insert_one(event_data)
            return True
        except Exception as e:
            print(f"Erreur log scaling: {e}")
            return False
    
    def get_scaling_history(self, container_name=None, limit=50):
        """Récupérer l'historique des événements de scaling"""
        try:
            query = {}
            if container_name:
                query['container_name'] = container_name
            
            cursor = self.scaling_events.find(query).sort('timestamp', -1).limit(limit)
            return list(cursor)
        except Exception as e:
            print(f"Erreur récupération historique scaling: {e}")
            return []
    
    def get_all_containers(self):
        """Récupérer la liste de tous les conteneurs"""
        try:
            return list(self.containers.find())
        except Exception as e:
            print(f"Erreur récupération conteneurs: {e}")
            return []
    
    def update_container_status(self, container_name, status):
        """Mettre à jour le statut d'un conteneur"""
        try:
            self.containers.update_one(
                {'name': container_name},
                {'$set': {'status': status, 'updated_at': datetime.now()}}
            )
            return True
        except Exception as e:
            print(f"Erreur mise à jour statut: {e}")
            return False
    
    def cleanup_old_metrics(self, days=30):
        """Nettoyer les anciennes métriques"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            result = self.metrics.delete_many({'timestamp': {'$lt': cutoff_date}})
            print(f"🗑️ {result.deleted_count} anciennes métriques supprimées")
            return True
        except Exception as e:
            print(f"Erreur nettoyage métriques: {e}")
            return False
    
    def get_training_data(self, container_name, days=7):
        """Récupérer les données pour l'entraînement ML"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            cursor = self.metrics.find({
                'container_name': container_name,
                'timestamp': {'$gte': cutoff_date}
            }).sort('timestamp', 1)
            
            data = list(cursor)
            return {
                'timestamps': [d['timestamp'] for d in data],
                'cpu': [d['cpu_percent'] for d in data],
                'memory': [d['memory_percent'] for d in data],
                'network_rx': [d['network_rx'] for d in data],
                'network_tx': [d['network_tx'] for d in data]
            }
        except Exception as e:
            print(f"Erreur récupération données training: {e}")
            return None