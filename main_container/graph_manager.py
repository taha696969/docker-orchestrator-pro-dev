import networkx as nx
import matplotlib.pyplot as plt
from datetime import datetime
import json


class GraphManager:
    def __init__(self):
        self.graph = nx.DiGraph()
        self.container_metadata = {}
    
    def add_container(self, container_name, metadata=None):
        """Ajouter un conteneur au graphe"""
        self.graph.add_node(container_name)
        if metadata:
            self.container_metadata[container_name] = metadata
        print(f"✅ Conteneur ajouté au graphe: {container_name}")
    
    def add_edge(self, from_container, to_container, weight=1, relation_type='depends_on'):
        """Ajouter une relation entre deux conteneurs"""
        # S'assurer que les nœuds existent
        if from_container not in self.graph:
            self.add_container(from_container)
        if to_container not in self.graph:
            self.add_container(to_container)
        
        # Ajouter l'arête avec métadonnées
        self.graph.add_edge(
            from_container, 
            to_container, 
            weight=weight,
            relation_type=relation_type,
            created_at=datetime.now()
        )
        print(f"🔗 Relation ajoutée: {from_container} -> {to_container} ({relation_type})")
    
    def remove_edge(self, from_container, to_container):
        try:
            if self.graph.has_edge(from_container, to_container):
                self.graph.remove_edge(from_container, to_container)
                print(f"❌ Relation retirée: {from_container} -> {to_container}")
                return True
            return False
        except Exception:
            return False
    
    def remove_container(self, container_name):
        """Supprimer un conteneur du graphe"""
        if container_name in self.graph:
            self.graph.remove_node(container_name)
            if container_name in self.container_metadata:
                del self.container_metadata[container_name]
            print(f"❌ Conteneur retiré du graphe: {container_name}")
    
    def prune_to_nodes(self, alive_nodes):
        """Supprime du graphe les nœuds qui ne font pas partie de alive_nodes."""
        try:
            keep = set(str(n) for n in (alive_nodes or []))
        except Exception:
            keep = set()

        for node in list(self.graph.nodes()):
            if str(node) not in keep:
                try:
                    self.graph.remove_node(node)
                except Exception:
                    pass
                try:
                    if node in self.container_metadata:
                        del self.container_metadata[node]
                except Exception:
                    pass
    
    def get_dependent_containers(self, container_name):
        """Récupérer tous les conteneurs qui dépendent d'un conteneur donné"""
        if container_name not in self.graph:
            return []
        
        # Conteneurs directement dépendants (successeurs)
        direct_dependents = list(self.graph.successors(container_name))
        
        # Conteneurs dont le conteneur dépend (prédécesseurs)
        dependencies = list(self.graph.predecessors(container_name))
        
        # Retourner la liste complète des conteneurs liés
        all_related = list(set(direct_dependents + dependencies))
        
        print(f"📊 Conteneurs liés à {container_name}: {all_related}")
        return all_related
    
    def get_all_descendants(self, container_name):
        """Récupérer tous les descendants d'un conteneur (récursif)"""
        if container_name not in self.graph:
            return []
        
        try:
            descendants = nx.descendants(self.graph, container_name)
            return list(descendants)
        except:
            return []
    
    def get_all_ancestors(self, container_name):
        """Récupérer tous les ancêtres d'un conteneur (récursif)"""
        if container_name not in self.graph:
            return []
        
        try:
            ancestors = nx.ancestors(self.graph, container_name)
            return list(ancestors)
        except:
            return []
    
    def get_critical_path(self, start_container, end_container):
        """Trouver le chemin critique entre deux conteneurs"""
        try:
            path = nx.shortest_path(self.graph, start_container, end_container)
            return path
        except nx.NetworkXNoPath:
            print(f"⚠️ Aucun chemin trouvé entre {start_container} et {end_container}")
            return []
        except Exception as e:
            print(f"Erreur calcul chemin: {e}")
            return []
    
    def detect_cycles(self):
        """Détecter les cycles dans le graphe (dépendances circulaires)"""
        try:
            cycles = list(nx.simple_cycles(self.graph))
            if cycles:
                print(f"⚠️ Cycles détectés: {cycles}")
            return cycles
        except Exception as e:
            print(f"Erreur détection cycles: {e}")
            return []
    
    def get_topology_order(self):
        """Obtenir l'ordre topologique des conteneurs"""
        try:
            return list(nx.topological_sort(self.graph))
        except nx.NetworkXError:
            print("⚠️ Le graphe contient des cycles, ordre topologique impossible")
            return []
    
    def get_container_degree(self, container_name):
        """Obtenir le degré d'un conteneur (nombre de connexions)"""
        if container_name not in self.graph:
            return {'in_degree': 0, 'out_degree': 0}
        
        return {
            'in_degree': self.graph.in_degree(container_name),
            'out_degree': self.graph.out_degree(container_name),
            'total_degree': self.graph.degree(container_name)
        }
    
    def find_critical_containers(self):
        """Identifier les conteneurs critiques (points de défaillance uniques)"""
        critical = []
        
        for node in self.graph.nodes():
            # Créer une copie du graphe sans ce nœud
            temp_graph = self.graph.copy()
            temp_graph.remove_node(node)
            
            # Vérifier si le graphe devient déconnecté
            if not nx.is_weakly_connected(temp_graph) and nx.is_weakly_connected(self.graph):
                critical.append(node)
        
        print(f"🎯 Conteneurs critiques identifiés: {critical}")
        return critical
    
    def get_cluster_coefficient(self, container_name):
        """Calculer le coefficient de clustering d'un conteneur"""
        try:
            # Convertir en graphe non-orienté pour le clustering
            undirected = self.graph.to_undirected()
            return nx.clustering(undirected, container_name)
        except:
            return 0.0
    
    def visualize_graph(self, save_path='graph_visualization.png'):
        """Visualiser le graphe des conteneurs"""
        try:
            plt.figure(figsize=(12, 8))
            
            # Calculer la position des nœuds
            pos = nx.spring_layout(self.graph, k=1, iterations=50)
            
            # Dessiner les nœuds
            nx.draw_networkx_nodes(
                self.graph, pos,
                node_color='lightblue',
                node_size=2000,
                alpha=0.9
            )
            
            # Dessiner les arêtes
            nx.draw_networkx_edges(
                self.graph, pos,
                edge_color='gray',
                arrows=True,
                arrowsize=20,
                width=2
            )
            
            # Dessiner les labels
            nx.draw_networkx_labels(
                self.graph, pos,
                font_size=10,
                font_weight='bold'
            )
            
            plt.title("Graphe des Relations entre Conteneurs", fontsize=16)
            plt.axis('off')
            plt.tight_layout()
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            print(f"📊 Graphe sauvegardé: {save_path}")
            return True
        except Exception as e:
            print(f"Erreur visualisation graphe: {e}")
            return False
    
    def export_to_json(self):
        """Exporter le graphe au format JSON"""
        try:
            data = nx.node_link_data(self.graph)
            return json.dumps(data, default=str, indent=2)
        except Exception as e:
            print(f"Erreur export JSON: {e}")
            return "{}"
    
    def import_from_json(self, json_data):
        """Importer un graphe depuis JSON"""
        try:
            data = json.loads(json_data)
            self.graph = nx.node_link_graph(data, directed=True)
            print("✅ Graphe importé avec succès")
            return True
        except Exception as e:
            print(f"Erreur import JSON: {e}")
            return False
    
    def get_graph_stats(self):
        """Obtenir des statistiques sur le graphe"""
        return {
            'total_containers': self.graph.number_of_nodes(),
            'total_relations': self.graph.number_of_edges(),
            'is_connected': nx.is_weakly_connected(self.graph),
            'has_cycles': len(list(nx.simple_cycles(self.graph))) > 0,
            'density': nx.density(self.graph),
            'critical_containers': self.find_critical_containers()
        }
    
    def suggest_scaling_targets(self, container_name):
        """Suggérer quels conteneurs dupliquer lors du scaling"""
        # Obtenir tous les conteneurs liés
        related = self.get_dependent_containers(container_name)
        
        # Obtenir les descendants (qui dépendent de ce conteneur)
        descendants = self.get_all_descendants(container_name)
        
        # Obtenir les ancêtres (dont ce conteneur dépend)
        ancestors = self.get_all_ancestors(container_name)
        
        # Combiner et dédupliquer
        all_targets = list(set(related + descendants + ancestors))
        
        return {
            'immediate': related,
            'descendants': descendants,
            'ancestors': ancestors,
            'all_targets': all_targets
        }