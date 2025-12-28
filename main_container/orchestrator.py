import docker
import threading
import time
import sys
import os
import json
import traceback
import uuid
from flask import Flask, request, jsonify
from collections import defaultdict
import numpy as np
from datetime import datetime
from flask_cors import CORS
import requests

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Imports avec gestion d'erreurs
try:
    from graph_manager import GraphManager
    from ml_predictor import MLPredictor
    from metrics_collector import MetricsCollector
    from database.mongo_handler import MongoHandler
    print("✓ Tous les modules importés avec succès")
except ImportError as e:
    print(f"✗ Erreur d'import: {e}")
    print("Assurez-vous que tous les fichiers sont présents:")
    print("  - graph_manager.py")
    print("  - ml_predictor.py")
    print("  - metrics_collector.py")
    print("  - mongo_handler.py")
    sys.exit(1)

app = Flask(__name__)
CORS(app)

class ContainerOrchestrator:
    def __init__(self):
        print("🚀 Initialisation de l'orchestrateur...")

        try:
            # Connexion Docker
            print("  → Connexion à Docker...")
            self.docker_client = docker.from_env()
            self.docker_client.ping()
            print("  ✓ Docker connecté")
        except Exception as e:
            print(f"  ✗ Erreur Docker: {e}")
            raise

        self.network_name = self._detect_network_name()
        print(f"  ✓ Réseau orchestrateur: {self.network_name}")

        try:
            # Initialisation des composants
            print("  → Initialisation GraphManager...")
            self.graph_manager = GraphManager()

            print("  → Initialisation MLPredictor...")
            self.ml_predictor = MLPredictor()

            print("  → Initialisation MetricsCollector...")
            self.metrics_collector = MetricsCollector()

            print("  → Connexion à MongoDB...")
            self.mongo_handler = MongoHandler()

            print("  ✓ Tous les composants initialisés")
        except Exception as e:
            print(f"  ✗ Erreur initialisation: {e}")
            traceback.print_exc()
            raise

        # Tracking des conteneurs actifs
        self.active_containers = {}
        self.container_metrics = defaultdict(list)
        self.load_threshold = 80
        self.scaling_cooldown = {}

        self.traffic_jobs = {}
        self.traffic_lock = threading.Lock()

        self._hydrate_graph_from_db()

        # Découvrir les conteneurs déjà démarrés (ex: worker_1/worker_2 via docker-compose)
        self.discover_existing_containers()

        # Démarrer le monitoring
        print("  → Démarrage du thread de monitoring...")
        self.monitoring_thread = threading.Thread(target=self.monitor_containers, daemon=True)
        self.monitoring_thread.start()
        print("  ✓ Monitoring démarré")

        print("✅ Orchestrateur initialisé avec succès\n")

    def create_container(self, image_name, container_name, env_vars=None, ports=None):
        """Créer un nouveau conteneur slave"""
        try:
            print(f"📦 Création du conteneur {container_name}...")

            env = dict(env_vars or {})
            image_lower = (image_name or '').lower()
            is_worker_image = ('worker' in image_lower) and ('nginx' not in image_lower) and ('mongo' not in image_lower)
            if is_worker_image:
                env.setdefault('CONTAINER_NAME', container_name)
                env.setdefault('ORCHESTRATOR_URL', 'http://main:5000')

            container = self.docker_client.containers.run(
                image=image_name,
                name=container_name,
                detach=True,
                environment=env,
                ports=ports or {},
                network=self.network_name
            )

            self.active_containers[container_name] = {
                'id': container.id,
                'container': container,
                'replicas': [],
                'created_at': datetime.now()
            }

            # Ajouter au graphe
            self.graph_manager.add_container(container_name, {
                'image': image_name,
                'created_at': datetime.now()
            })

            # Enregistrer dans MongoDB
            self.mongo_handler.insert_container_info({
                'name': container_name,
                'id': container.id,
                'created_at': datetime.now(),
                'status': 'running',
                'image': image_name
            })

            if is_worker_image:
                try:
                    self.graph_manager.add_edge('orchestrator_main', container_name, relation_type='master_of')
                    self.mongo_handler.insert_relation('orchestrator_main', container_name, relation_type='master_of')
                except Exception:
                    pass

            print(f"✓ Conteneur {container_name} créé")
            return container
        except Exception as e:
            print(f"✗ Erreur création conteneur {container_name}: {e}")
            traceback.print_exc()
            return None

    def discover_existing_containers(self):
        """Découvrir et inscrire les conteneurs déjà en cours d'exécution sur le réseau."""
        try:
            containers = self.docker_client.containers.list()
            excluded = {
                'orchestrator_main',
                'orchestrator_mongodb',
                'orchestrator_web'
            }

            pending_replica_links = []

            for container in containers:
                try:
                    if container.name in self.active_containers:
                        continue

                    networks = container.attrs.get('NetworkSettings', {}).get('Networks', {})
                    if self.network_name not in networks:
                        continue

                    # Toujours ajouter au graphe (même si exclu du monitoring)
                    try:
                        self.graph_manager.add_container(container.name, {
                            'image': container.attrs.get('Config', {}).get('Image'),
                            'created_at': datetime.now()
                        })
                    except Exception:
                        pass

                    if container.name in excluded:
                        continue

                    self.active_containers[container.name] = {
                        'id': container.id,
                        'container': container,
                        'replicas': [],
                        'created_at': datetime.now()
                    }
                    self.graph_manager.add_container(container.name, {
                        'image': container.attrs.get('Config', {}).get('Image'),
                        'created_at': datetime.now()
                    })

                    try:
                        if '_replica_' in container.name:
                            parent = container.name.rsplit('_replica_', 1)[0]
                            self.active_containers[container.name]['parent'] = parent
                            pending_replica_links.append((parent, container.name))

                            # Une réplique ne doit pas être directement master_of
                            try:
                                self.graph_manager.remove_edge('orchestrator_main', container.name)
                            except Exception:
                                pass
                            try:
                                self.mongo_handler.remove_relation('orchestrator_main', container.name, relation_type='master_of')
                            except Exception:
                                pass
                    except Exception:
                        pass

                    try:
                        image_name = container.attrs.get('Config', {}).get('Image')
                        image_lower = (image_name or '').lower()
                        is_worker_image = ('worker' in image_lower) and ('nginx' not in image_lower) and ('mongo' not in image_lower)
                        if is_worker_image:
                            if '_replica_' not in container.name:
                                self.graph_manager.add_edge('orchestrator_main', container.name, relation_type='master_of')
                                self.mongo_handler.insert_relation('orchestrator_main', container.name, relation_type='master_of')
                    except Exception:
                        pass
                except Exception:
                    continue

            for parent, replica_name in pending_replica_links:
                try:
                    if parent in self.active_containers:
                        if replica_name not in self.active_containers[parent].get('replicas', []):
                            self.active_containers[parent].setdefault('replicas', []).append(replica_name)

                    try:
                        self.graph_manager.add_edge(parent, replica_name, relation_type='replica_of')
                        self.mongo_handler.insert_relation(parent, replica_name, relation_type='replica_of')
                    except Exception:
                        pass
                except Exception:
                    continue

            if self.active_containers:
                print(f"  ✓ Conteneurs découverts: {list(self.active_containers.keys())}")
        except Exception as e:
            print(f"  ⚠ Erreur discovery conteneurs: {e}")

    def _hydrate_graph_from_db(self):
        try:
            containers = self.mongo_handler.get_all_containers() or []
            for c in containers:
                name = c.get('name')
                if name:
                    self.graph_manager.add_container(name, {
                        'image': c.get('image'),
                        'created_at': c.get('created_at')
                    })

            try:
                relations = list(self.mongo_handler.relations.find())
            except Exception:
                relations = []

            for r in relations:
                frm = r.get('from_container')
                to = r.get('to_container')
                rel_type = r.get('relation_type', 'depends_on')
                if frm and to:
                    self.graph_manager.add_edge(frm, to, relation_type=rel_type)
        except Exception:
            return

    def monitor_containers(self):
        """Surveiller les métriques des conteneurs en continu"""
        print("🔍 Thread de monitoring actif")

        while True:
            try:
                # Re-découvrir régulièrement les conteneurs (workers démarrés après main)
                self.discover_existing_containers()

                if not self.active_containers:
                    time.sleep(5)
                    continue

                for container_name, container_info in list(self.active_containers.items()):
                    try:
                        container = container_info['container']
                        container.reload()  # Rafraîchir l'état

                        # Vérifier si le conteneur est en cours d'exécution
                        if container.status != 'running':
                            print(f"⚠ Conteneur {container_name} n'est pas en cours d'exécution (status: {container.status})")
                            continue

                        # Récupérer les stats
                        stats = container.stats(stream=False)
                        metrics = self.metrics_collector.parse_stats(stats)

                        # Stocker les métriques
                        self.container_metrics[container_name].append({
                            'timestamp': datetime.now().isoformat(),
                            'cpu_percent': metrics['cpu_percent'],
                            'memory_percent': metrics['memory_percent'],
                            'network_rx': metrics['network_rx'],
                            'network_tx': metrics['network_tx']
                        })

                        # Limiter l'historique à 100 entrées
                        if len(self.container_metrics[container_name]) > 100:
                            self.container_metrics[container_name] = self.container_metrics[container_name][-100:]

                        # Sauvegarder dans MongoDB
                        self.mongo_handler.insert_metrics(container_name, metrics)

                        # Vérifier si scaling nécessaire
                        self.check_scaling_need(container_name, metrics)

                    except Exception as e:
                        print(f"⚠ Erreur monitoring {container_name}: {e}")
                        continue

                time.sleep(5)

            except Exception as e:
                print(f"⚠ Erreur boucle monitoring: {e}")
                time.sleep(5)

    def check_scaling_need(self, container_name, current_metrics):
        """Vérifier si le conteneur nécessite un scaling"""
        try:
            # Éviter le scaling trop fréquent
            if container_name in self.scaling_cooldown:
                if (datetime.now() - self.scaling_cooldown[container_name]).seconds < 60:
                    return

            # Récupérer l'historique
            historical_data = self.container_metrics[container_name][-20:]

            if len(historical_data) < 10:
                return

            # Préparer les données pour le modèle ML
            cpu_values = [m['cpu_percent'] for m in historical_data]
            mem_values = [m['memory_percent'] for m in historical_data]

            # Prédire la charge future
            prediction = self.ml_predictor.predict_load(cpu_values, mem_values)

            # Si prédiction dépasse le seuil
            if prediction['predicted_cpu'] > self.load_threshold or prediction['should_scale']:
                print(f"🚀 Scaling nécessaire pour {container_name}")
                print(f"   CPU prédit: {prediction['predicted_cpu']:.2f}%")

                # Déclencher le scaling
                self.scale_container(container_name)
                self.scaling_cooldown[container_name] = datetime.now()

        except Exception as e:
            print(f"⚠ Erreur check_scaling_need: {e}")

    def scale_container(self, container_name):
        """Dupliquer un conteneur et ses dépendances"""
        try:
            if container_name not in self.active_containers:
                print(f"✗ Conteneur {container_name} introuvable")
                return

            # Obtenir les conteneurs à dupliquer (cascade via graphe)
            scaling_targets = self.graph_manager.suggest_scaling_targets(container_name)
            related_containers = scaling_targets.get('all_targets', [])

            # Dupliquer le conteneur principal
            created_replicas = {}
            replica_name = self._create_replica(container_name)
            if replica_name:
                created_replicas[container_name] = replica_name

            if replica_name:
                # Dupliquer les conteneurs liés
                for related in related_containers:
                    if related == container_name:
                        continue
                    if related in self.active_containers:
                        r = self._create_replica(related)
                        if r:
                            created_replicas[related] = r

                # Si des conteneurs parents sont liés entre eux, lier aussi leurs répliques (par round de scaling)
                try:
                    for u, v, data in self.graph_manager.graph.edges(data=True):
                        if u in created_replicas and v in created_replicas:
                            rel_type = (data or {}).get('relation_type')
                            if rel_type in ('master_of', 'replica_of'):
                                continue
                            self.graph_manager.add_edge(created_replicas[u], created_replicas[v], relation_type=rel_type)
                            try:
                                self.mongo_handler.insert_relation(created_replicas[u], created_replicas[v], relation_type=rel_type)
                            except Exception:
                                pass
                except Exception:
                    pass

                print(f"✅ Scaling terminé: {container_name} -> {replica_name}")
                print(f"   Conteneurs liés dupliqués: {related_containers}")

                # Logger l'événement
                self.mongo_handler.log_scaling_event(container_name, 'scale_up', {
                    'replica': replica_name,
                    'related': related_containers
                })

        except Exception as e:
            print(f"✗ Erreur scaling {container_name}: {e}")
            traceback.print_exc()

    def _create_replica(self, original_name):
        """Créer une réplique d'un conteneur"""
        try:
            if original_name not in self.active_containers:
                return None

            original_container = self.active_containers[original_name]['container']
            original_container.reload()

            # Générer un nom unique
            replica_count = len(self.active_containers[original_name]['replicas'])
            replica_name = f"{original_name}_replica_{replica_count + 1}"

            # Récupérer la configuration
            config = original_container.attrs
            image = config['Config']['Image']
            env = config['Config']['Env']

            # Créer la réplique
            replica = self.docker_client.containers.run(
                image=image,
                name=replica_name,
                detach=True,
                environment=env,
                network=self.network_name
            )

            # Enregistrer
            self.active_containers[original_name]['replicas'].append(replica_name)
            self.active_containers[replica_name] = {
                'id': replica.id,
                'container': replica,
                'replicas': [],
                'created_at': datetime.now(),
                'parent': original_name
            }

            try:
                self.graph_manager.add_container(replica_name, {
                    'image': image,
                    'created_at': datetime.now(),
                    'parent': original_name
                })
                self.graph_manager.add_edge(original_name, replica_name, relation_type='replica_of')
            except Exception:
                pass

            try:
                self.mongo_handler.insert_container_info({
                    'name': replica_name,
                    'id': replica.id,
                    'created_at': datetime.now(),
                    'status': 'running',
                    'image': image,
                    'parent': original_name
                })
                self.mongo_handler.insert_relation(original_name, replica_name, relation_type='replica_of')
            except Exception:
                pass

            try:
                # Une réplique ne doit pas être directement master_of (elle reste liée à son parent via replica_of)
                self.graph_manager.remove_edge('orchestrator_main', replica_name)
            except Exception:
                pass

            try:
                self.mongo_handler.remove_relation('orchestrator_main', replica_name, relation_type='master_of')
            except Exception:
                pass

            print(f"✓ Réplique créée: {replica_name}")
            return replica_name

        except Exception as e:
            print(f"✗ Erreur création réplique: {e}")
            return None

    def route_request(self, container_name, payload):
        """Router une requête vers le conteneur le moins chargé"""
        try:
            if isinstance(payload, dict) and payload.get('__direct_instance'):
                payload = dict(payload)
                payload.pop('__direct_instance', None)
                return self._send_request_to_container(container_name, payload)
        except Exception:
            pass

        instances = [container_name]
        if container_name in self.active_containers:
            instances.extend(self.active_containers[container_name]['replicas'])

        best_instance = self._select_best_instance(instances)
        return self._send_request_to_container(best_instance, payload)

    def _select_best_instance(self, instances):
        """Sélectionner l'instance avec la charge la plus faible"""
        min_load = float('inf')
        best_instance = instances[0]

        for instance in instances:
            if instance in self.container_metrics and self.container_metrics[instance]:
                recent_metrics = self.container_metrics[instance][-1]
                current_load = recent_metrics['cpu_percent']

                if current_load < min_load:
                    min_load = current_load
                    best_instance = instance

        return best_instance

    def _send_request_to_container(self, container_name, payload):
        """Envoyer une requête à un conteneur spécifique"""
        try:
            url = f"http://{container_name}:5001/process"
            response = requests.post(url, json=payload, timeout=10)

            return {
                'target': container_name,
                'status_code': response.status_code,
                'response': response.json() if response.content else None
            }
        except Exception as e:
            return {
                'target': container_name,
                'url': f"http://{container_name}:5001/process",
                'error': str(e)
            }

    def _detect_network_name(self):
        """Détecter automatiquement le réseau Docker utilisé par l'orchestrateur (compose network préfixé)."""
        explicit = os.getenv('ORCHESTRATOR_NETWORK')
        if explicit:
            return explicit

        # HOSTNAME dans un conteneur = container id
        self_id = os.getenv('HOSTNAME')
        if self_id:
            try:
                me = self.docker_client.containers.get(self_id)
                networks = (me.attrs.get('NetworkSettings', {}) or {}).get('Networks', {}) or {}
                if networks:
                    return next(iter(networks.keys()))
            except Exception:
                pass

        # Fallbacks
        for candidate in ['worker-slave_orchestrator_network', 'orchestrator_network']:
            try:
                self.docker_client.networks.get(candidate)
                return candidate
            except Exception:
                continue

        return 'orchestrator_network'

    def start_traffic(self, target_container, rps=5, complexity=1, duration_seconds=None):
        traffic_id = str(uuid.uuid4())
        stop_event = threading.Event()

        job = {
            'id': traffic_id,
            'target': target_container,
            'rps': float(rps),
            'complexity': int(complexity),
            'duration_seconds': duration_seconds,
            'direct': True,
            'started_at': datetime.now().isoformat(),
            'stopped_at': None,
            'sent': 0,
            'errors': 0,
            'last_error': None,
            'last_target': None,
            'last_status_code': None,
            'running': True
        }

        def _traffic_loop():
            started = time.time()
            sleep_s = 0.0
            try:
                if job['rps'] > 0:
                    sleep_s = 1.0 / job['rps']
            except Exception:
                sleep_s = 0.0

            while not stop_event.is_set():
                if duration_seconds is not None and (time.time() - started) >= duration_seconds:
                    break

                try:
                    payload = {'complexity': job['complexity']}
                    if job.get('direct'):
                        payload['__direct_instance'] = True

                    result = self.route_request(target_container, payload)
                    with self.traffic_lock:
                        job['last_target'] = result.get('target') if isinstance(result, dict) else None
                        job['last_status_code'] = result.get('status_code') if isinstance(result, dict) else None

                        if isinstance(result, dict) and result.get('error'):
                            job['errors'] += 1
                            job['last_error'] = result.get('error')
                        else:
                            job['sent'] += 1
                except Exception as e:
                    with self.traffic_lock:
                        job['errors'] += 1
                        job['last_error'] = str(e)

                if sleep_s > 0:
                    time.sleep(sleep_s)

            with self.traffic_lock:
                job['running'] = False
                job['stopped_at'] = datetime.now().isoformat()

        thread = threading.Thread(target=_traffic_loop, daemon=True)
        with self.traffic_lock:
            self.traffic_jobs[traffic_id] = {
                'job': job,
                'stop_event': stop_event,
                'thread': thread
            }

        thread.start()
        return job

    def stop_traffic(self, traffic_id):
        with self.traffic_lock:
            item = self.traffic_jobs.get(traffic_id)
            if not item:
                return None
            item['stop_event'].set()
            return item['job']

    def list_traffic(self):
        with self.traffic_lock:
            return [item['job'] for item in self.traffic_jobs.values()]


# Instance globale
print("=" * 60)
print("🐳 Démarrage de l'Orchestrateur Docker Intelligent")
print("=" * 60)
print()

try:
    orchestrator = ContainerOrchestrator()
except Exception as e:
    print(f"\n❌ ERREUR FATALE lors de l'initialisation:")
    print(f"   {e}")
    traceback.print_exc()
    sys.exit(1)

# Routes Flask
@app.route('/container/create', methods=['POST'])
def create_container():
    try:
        data = request.json
        container = orchestrator.create_container(
            image_name=data['image'],
            container_name=data['name'],
            env_vars=data.get('env'),
            ports=data.get('ports')
        )

        if container:
            return jsonify({'status': 'created', 'id': container.id})
        else:
            return jsonify({'error': 'Failed to create container'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/container/<name>/metrics', methods=['GET'])
def get_metrics(name):
    metrics = orchestrator.container_metrics.get(name, [])
    return jsonify(metrics[-10:])


@app.route('/relation/add', methods=['POST'])
def add_relation():
    try:
        data = request.json
        relation_type = data.get('type', 'depends_on')
        orchestrator.graph_manager.add_edge(data['from'], data['to'], relation_type=relation_type)
        orchestrator.mongo_handler.insert_relation(data['from'], data['to'], relation_type=relation_type)
        return jsonify({'status': 'relation added'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/relation/remove', methods=['POST'])
def remove_relation():
    try:
        data = request.json or {}
        from_c = data.get('from')
        to_c = data.get('to')
        if not from_c or not to_c:
            return jsonify({'error': 'Missing from/to'}), 400

        rel_type = data.get('type')

        if rel_type:
            try:
                if orchestrator.graph_manager.graph.has_edge(from_c, to_c):
                    current_type = (orchestrator.graph_manager.graph.edges[from_c, to_c] or {}).get('relation_type')
                    if current_type and current_type != rel_type:
                        return jsonify({'status': 'not_found', 'removed': 0})
            except Exception:
                pass

        removed_db = orchestrator.mongo_handler.remove_relation(from_c, to_c, relation_type=rel_type)

        removed_graph = orchestrator.graph_manager.remove_edge(from_c, to_c)
        if removed_graph is False and removed_db == 0:
            return jsonify({'status': 'not_found', 'removed': 0})

        return jsonify({'status': 'removed', 'removed': removed_db})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/route/<name>', methods=['POST'])
def route_to_container(name):
    try:
        payload = request.json or {}
        result = orchestrator.route_request(name, payload)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/traffic/start', methods=['POST'])
def start_traffic():
    try:
        data = request.json or {}
        target = data.get('target')
        if not target:
            return jsonify({'error': 'Missing target'}), 400

        rps = float(data.get('rps', 5))
        complexity = int(data.get('complexity', 1))
        duration = data.get('duration_seconds')
        duration_seconds = float(duration) if duration is not None else None

        direct = data.get('direct', True)
        direct = bool(direct)

        job = orchestrator.start_traffic(
            target_container=target,
            rps=rps,
            complexity=complexity,
            duration_seconds=duration_seconds
        )

        # Refléter le mode direct dans le job renvoyé et stocké
        job['direct'] = direct

        with orchestrator.traffic_lock:
            item = orchestrator.traffic_jobs.get(job['id'])
            if item and 'job' in item:
                item['job']['direct'] = direct

        return jsonify({'status': 'started', 'job': job})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/traffic/stop', methods=['POST'])
def stop_traffic():
    try:
        data = request.json or {}
        traffic_id = data.get('id')
        if not traffic_id:
            return jsonify({'error': 'Missing id'}), 400

        job = orchestrator.stop_traffic(traffic_id)
        if not job:
            return jsonify({'error': 'Unknown id'}), 404

        return jsonify({'status': 'stopping', 'job': job})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/traffic/status', methods=['GET'])
def traffic_status():
    try:
        return jsonify({'jobs': orchestrator.list_traffic()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/containers/list', methods=['GET'])
def list_containers():
    orchestrator.discover_existing_containers()
    containers = []
    for name, info in orchestrator.active_containers.items():
        containers.append({
            'name': name,
            'id': info['id'],
            'created_at': info['created_at'].isoformat(),
            'replicas': info.get('replicas', [])
        })
    return jsonify({'containers': containers})


@app.route('/container/<name>/stop', methods=['POST'])
def stop_container(name):
    try:
        if name in orchestrator.active_containers:
            container = orchestrator.active_containers[name]['container']
            container.stop()
            orchestrator.mongo_handler.update_container_status(name, 'stopped')
            return jsonify({'status': 'stopped', 'name': name})
        return jsonify({'error': 'Container not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/container/<name>/start', methods=['POST'])
def start_container(name):
    try:
        if name in orchestrator.active_containers:
            container = orchestrator.active_containers[name]['container']
            container.start()
            orchestrator.mongo_handler.update_container_status(name, 'running')
            return jsonify({'status': 'started', 'name': name})
        return jsonify({'error': 'Container not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/container/<name>/remove', methods=['DELETE'])
def remove_container(name):
    try:
        if name == 'orchestrator_main':
            return jsonify({'error': 'Cannot remove orchestrator_main'}), 400
        if name in orchestrator.active_containers:
            container = orchestrator.active_containers[name]['container']
            container.stop()
            container.remove()
            del orchestrator.active_containers[name]
            orchestrator.graph_manager.remove_container(name)
            orchestrator.mongo_handler.update_container_status(name, 'removed')
            return jsonify({'status': 'removed', 'name': name})
        return jsonify({'error': 'Container not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/graph/stats', methods=['GET'])
def get_graph_stats():
    stats = orchestrator.graph_manager.get_graph_stats()
    return jsonify(stats)


@app.route('/graph/export', methods=['GET'])
def export_graph():
    try:
        orchestrator.discover_existing_containers()
    except Exception:
        pass
    graph_json = orchestrator.graph_manager.export_to_json()
    try:
        graph_obj = json.loads(graph_json) if isinstance(graph_json, str) else graph_json
    except Exception:
        graph_obj = {}
    hidden = {'orchestrator_mongodb', 'orchestrator_web'}
    try:
        nodes = graph_obj.get('nodes', []) or []
        links = graph_obj.get('links', []) or []
        filtered_nodes = []
        for n in nodes:
            node_id = n.get('id') if isinstance(n, dict) else n
            if str(node_id) in hidden:
                continue
            filtered_nodes.append(n)

        filtered_links = []
        for l in links:
            src = str(l.get('source'))
            tgt = str(l.get('target'))
            if src in hidden or tgt in hidden:
                continue
            filtered_links.append(l)

        graph_obj = dict(graph_obj)
        graph_obj['nodes'] = filtered_nodes
        graph_obj['links'] = filtered_links
    except Exception:
        pass
    return jsonify({'graph': graph_obj})


@app.route('/scaling/history', methods=['GET'])
def get_scaling_history():
    container_name = request.args.get('container')
    limit = int(request.args.get('limit', 50))
    history = orchestrator.mongo_handler.get_scaling_history(container_name, limit)
    return jsonify({'history': history})


@app.route('/ml/train', methods=['POST'])
def train_ml_model():
    try:
        container_name = request.json.get('container_name')
        days = request.json.get('days', 7)
       
        training_data = orchestrator.mongo_handler.get_training_data(container_name, days)
       
        if not training_data:
            return jsonify({'error': 'Pas assez de données'}), 400
       
        historical_data = []
        for i in range(len(training_data['timestamps'])):
            historical_data.append({
                'timestamp': training_data['timestamps'][i],
                'cpu_percent': training_data['cpu'][i],
                'memory_percent': training_data['memory'][i]
            })
       
        success = orchestrator.ml_predictor.train_model(historical_data)
       
        if success:
            return jsonify({'status': 'trained', 'samples': len(historical_data)})
        else:
            return jsonify({'error': 'Training failed'}), 500
           
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    try:
        mongo_ok = orchestrator.mongo_handler.client is not None
        if mongo_ok:
            try:
                orchestrator.mongo_handler.client.server_info()
            except:
                mongo_ok = False
       
        return jsonify({
            'status': 'healthy',
            'services': {
                'orchestrator': 'running',
                'mongodb': 'connected' if mongo_ok else 'disconnected',
                'docker': 'connected'
            },
            'stats': {
                'active_containers': len(orchestrator.active_containers),
                'monitored_containers': len(orchestrator.container_metrics)
            }
        })
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500


@app.route('/predict/<name>', methods=['GET'])
def predict_load(name):
    try:
        if name not in orchestrator.container_metrics:
            return jsonify({'error': 'No metrics available'}), 404
       
        metrics = orchestrator.container_metrics[name]
        if len(metrics) < 10:
            return jsonify({'error': 'Not enough data'}), 400
       
        cpu_values = [m['cpu_percent'] for m in metrics[-20:]]
        mem_values = [m['memory_percent'] for m in metrics[-20:]]
       
        prediction = orchestrator.ml_predictor.predict_load(cpu_values, mem_values)
       
        return jsonify(prediction)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/', methods=['GET'])
def index():
    return jsonify({
        'service': 'Docker Orchestrator',
        'status': 'running',
        'version': '1.0.0'
    })


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🌐 Démarrage du serveur Flask sur http://0.0.0.0:5000")
    print("=" * 60)
    print()
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    except Exception as e:
        print(f"\n❌ Erreur démarrage Flask: {e}")
        traceback.print_exc()
        sys.exit(1)