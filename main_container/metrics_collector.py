import time
from datetime import datetime

class MetricsCollector:
    def __init__(self):
        self.previous_stats = {}
    
    def parse_stats(self, stats):
        """Parser les statistiques Docker et calculer les métriques"""
        try:
            # CPU
            cpu_stats = stats['cpu_stats']
            precpu_stats = stats['precpu_stats']
            
            cpu_percent = self._calculate_cpu_percent(cpu_stats, precpu_stats)
            
            # Mémoire
            memory_stats = stats['memory_stats']
            memory_usage = memory_stats.get('usage', 0)
            memory_limit = memory_stats.get('limit', 1)
            memory_percent = (memory_usage / memory_limit) * 100 if memory_limit > 0 else 0
            
            # Réseau
            network_stats = stats.get('networks', {})
            network_rx = 0
            network_tx = 0
            
            for interface, data in network_stats.items():
                network_rx += data.get('rx_bytes', 0)
                network_tx += data.get('tx_bytes', 0)
            
            # Disque I/O
            blkio_stats = stats.get('blkio_stats', {})
            block_read = 0
            block_write = 0
            
            io_service_bytes = blkio_stats.get('io_service_bytes_recursive', [])
            for entry in io_service_bytes:
                if entry.get('op') == 'Read':
                    block_read += entry.get('value', 0)
                elif entry.get('op') == 'Write':
                    block_write += entry.get('value', 0)
            
            return {
                'timestamp': datetime.now(),
                'cpu_percent': round(cpu_percent, 2),
                'memory_percent': round(memory_percent, 2),
                'memory_usage': memory_usage,
                'memory_limit': memory_limit,
                'network_rx': network_rx,
                'network_tx': network_tx,
                'block_read': block_read,
                'block_write': block_write
            }
        
        except Exception as e:
            print(f"Erreur parsing stats: {e}")
            return self._default_metrics()
    
    def _calculate_cpu_percent(self, cpu_stats, precpu_stats):
        """Calculer le pourcentage d'utilisation CPU"""
        try:
            cpu_delta = cpu_stats['cpu_usage']['total_usage'] - \
                       precpu_stats['cpu_usage']['total_usage']
            
            system_delta = cpu_stats['system_cpu_usage'] - \
                          precpu_stats['system_cpu_usage']
            
            online_cpus = cpu_stats.get('online_cpus', 
                         len(cpu_stats['cpu_usage'].get('percpu_usage', [1])))
            
            if system_delta > 0 and cpu_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * online_cpus * 100
                return min(cpu_percent, 100.0)
            
            return 0.0
        
        except Exception as e:
            return 0.0
    
    def _default_metrics(self):
        """Métriques par défaut en cas d'erreur"""
        return {
            'timestamp': datetime.now(),
            'cpu_percent': 0.0,
            'memory_percent': 0.0,
            'memory_usage': 0,
            'memory_limit': 0,
            'network_rx': 0,
            'network_tx': 0,
            'block_read': 0,
            'block_write': 0
        }
    
    def calculate_network_throughput(self, container_name, current_stats):
        """Calculer le débit réseau (bytes/sec)"""
        if container_name not in self.previous_stats:
            self.previous_stats[container_name] = {
                'timestamp': datetime.now(),
                'network_rx': current_stats['network_rx'],
                'network_tx': current_stats['network_tx']
            }
            return {'rx_throughput': 0, 'tx_throughput': 0}
        
        prev = self.previous_stats[container_name]
        time_delta = (datetime.now() - prev['timestamp']).total_seconds()
        
        if time_delta == 0:
            return {'rx_throughput': 0, 'tx_throughput': 0}
        
        rx_throughput = (current_stats['network_rx'] - prev['network_rx']) / time_delta
        tx_throughput = (current_stats['network_tx'] - prev['network_tx']) / time_delta
        
        # Mettre à jour les stats précédentes
        self.previous_stats[container_name] = {
            'timestamp': datetime.now(),
            'network_rx': current_stats['network_rx'],
            'network_tx': current_stats['network_tx']
        }
        
        return {
            'rx_throughput': round(rx_throughput, 2),
            'tx_throughput': round(tx_throughput, 2)
        }
    
    def calculate_disk_iops(self, container_name, current_stats):
        """Calculer les IOPS du disque"""
        if container_name not in self.previous_stats:
            self.previous_stats[container_name] = {
                'timestamp': datetime.now(),
                'block_read': current_stats['block_read'],
                'block_write': current_stats['block_write']
            }
            return {'read_iops': 0, 'write_iops': 0}
        
        prev = self.previous_stats[container_name]
        time_delta = (datetime.now() - prev['timestamp']).total_seconds()
        
        if time_delta == 0:
            return {'read_iops': 0, 'write_iops': 0}
        
        read_iops = (current_stats['block_read'] - prev['block_read']) / time_delta
        write_iops = (current_stats['block_write'] - prev['block_write']) / time_delta
        
        return {
            'read_iops': round(read_iops, 2),
            'write_iops': round(write_iops, 2)
        }
    
    def get_health_score(self, metrics):
        """Calculer un score de santé du conteneur (0-100)"""
        score = 100
        
        # Pénalités basées sur l'utilisation
        if metrics['cpu_percent'] > 80:
            score -= (metrics['cpu_percent'] - 80) * 2
        elif metrics['cpu_percent'] > 60:
            score -= (metrics['cpu_percent'] - 60)
        
        if metrics['memory_percent'] > 80:
            score -= (metrics['memory_percent'] - 80) * 2
        elif metrics['memory_percent'] > 60:
            score -= (metrics['memory_percent'] - 60)
        
        return max(0, min(100, score))