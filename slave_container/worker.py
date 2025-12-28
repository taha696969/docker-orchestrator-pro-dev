from flask import Flask, request, jsonify
import psutil
import time
import os
import threading
from datetime import datetime

app = Flask(__name__)

class Worker:
    def __init__(self):
        self.container_name = os.getenv('CONTAINER_NAME', 'worker_unknown')
        self.orchestrator_url = os.getenv('ORCHESTRATOR_URL', 'http://main:5000')
        self.metrics_buffer = []
        self.is_running = True
        
        # Démarrer l'export de métriques
        self.metrics_thread = threading.Thread(target=self.export_metrics_loop, daemon=True)
        self.metrics_thread.start()
    
    def get_current_metrics(self):
        """Collecter les métriques actuelles du conteneur"""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        network = psutil.net_io_counters()
        
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'container_name': self.container_name,
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
            'memory_used': memory.used,
            'memory_total': memory.total,
            'disk_percent': disk.percent,
            'network_sent': network.bytes_sent,
            'network_recv': network.bytes_recv
        }
        
        return metrics
    
    def export_metrics_loop(self):
        """Exporter les métriques vers l'orchestrateur"""
        while self.is_running:
            try:
                metrics = self.get_current_metrics()
                self.metrics_buffer.append(metrics)
                
                # Garder seulement les 100 dernières métriques en mémoire
                if len(self.metrics_buffer) > 100:
                    self.metrics_buffer.pop(0)
                
                time.sleep(5)  # Exporter toutes les 5 secondes
            
            except Exception as e:
                print(f"Erreur export métriques: {e}")
                time.sleep(5)
    
    def process_request(self, data):
        """Traiter une requête (simule un travail)"""
        # Simuler un traitement
        complexity = data.get('complexity', 1)
        
        start_time = time.time()
        
        # Simulation de charge CPU
        result = 0
        for i in range(complexity * 100000):
            result += i * i
        
        processing_time = time.time() - start_time
        
        return {
            'status': 'success',
            'container': self.container_name,
            'processing_time': processing_time,
            'result': result % 1000000  # Résultat simplifié
        }

# Instance globale du worker
worker = Worker()

@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint de vérification de santé"""
    return jsonify({
        'status': 'healthy',
        'container': worker.container_name,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/metrics', methods=['GET'])
def get_metrics():
    """Endpoint pour récupérer les métriques"""
    current_metrics = worker.get_current_metrics()
    return jsonify(current_metrics)

@app.route('/metrics/history', methods=['GET'])
def get_metrics_history():
    """Récupérer l'historique des métriques"""
    return jsonify({
        'container': worker.container_name,
        'metrics': worker.metrics_buffer[-20:]  # 20 dernières métriques
    })

@app.route('/process', methods=['POST'])
def process_request():
    """Traiter une requête"""
    data = request.json
    result = worker.process_request(data)
    return jsonify(result)

@app.route('/status', methods=['GET'])
def get_status():
    """Obtenir le statut détaillé du worker"""
    metrics = worker.get_current_metrics()
    return jsonify({
        'container': worker.container_name,
        'status': 'running',
        'uptime': time.time(),
        'current_metrics': metrics,
        'orchestrator': worker.orchestrator_url
    })

if __name__ == '__main__':
    print(f"🚀 Worker {worker.container_name} démarré")
    app.run(host='0.0.0.0', port=5001)