#!/bin/bash

# Script de démarrage complet du système d'orchestration

echo "=========================================="
echo "🐳 Orchestrateur Docker Intelligent"
echo "=========================================="
echo ""

# Couleurs pour le terminal
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Fonction pour afficher les étapes
step() {
    echo -e "${BLUE}[ÉTAPE]${NC} $1"
}

success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

error() {
    echo -e "${RED}[ERREUR]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[ATTENTION]${NC} $1"
}

# Vérifier que Docker est installé
step "Vérification de Docker..."
if ! command -v docker &> /dev/null; then
    error "Docker n'est pas installé"
    exit 1
fi
success "Docker détecté"

# Vérifier que Docker Compose est installé
step "Vérification de Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    error "Docker Compose n'est pas installé"
    exit 1
fi
success "Docker Compose détecté"

# Créer les répertoires nécessaires
step "Création de la structure de répertoires..."
mkdir -p models data docker main_container slave_container database interface/templates

success "Répertoires créés"

# Créer le réseau Docker
step "Création du réseau Docker..."
docker network create orchestrator_network 2>/dev/null || true
success "Réseau orchestrator_network créé"

# Construire les images Docker
step "Construction des images Docker..."
echo "  - Construction de l'image orchestrateur..."
docker build -t orchestrator-main -f docker/Dockerfile.main .

echo "  - Construction de l'image worker..."
docker build -t orchestrator-worker -f docker/Dockerfile.slave .

success "Images Docker construites"

# Démarrer MongoDB
step "Démarrage de MongoDB..."
docker-compose up -d mongodb
sleep 5
success "MongoDB démarré"

# Démarrer le conteneur principal
step "Démarrage du conteneur orchestrateur..."
docker-compose up -d main
sleep 5
success "Orchestrateur démarré"

# Démarrer les workers initiaux
step "Démarrage des workers initiaux..."
docker-compose up -d worker1 worker2
success "Workers démarrés"

# Attendre que tous les services soient prêts
step "Attente du démarrage complet des services..."
sleep 10

# Vérifier l'état des conteneurs
step "Vérification de l'état des conteneurs..."
docker-compose ps

echo ""
echo "=========================================="
success "✅ Système d'orchestration démarré avec succès!"
echo "=========================================="
echo ""
echo "📊 Accès aux services:"
echo "   - Interface Web: http://localhost:8080"
echo "   - API Orchestrateur: http://localhost:5000"
echo "   - MongoDB: mongodb://localhost:27017"
echo ""
echo "📝 Commandes utiles:"
echo "   - Voir les logs: docker-compose logs -f"
echo "   - Arrêter le système: docker-compose down"
echo "   - Redémarrer: docker-compose restart"
echo ""
echo "🔧 Pour entraîner le modèle ML:"
echo "   docker exec -it orchestrator_main python models/train_model.py"
echo ""
echo "🧪 Pour générer des données de test:"
echo "   docker exec -it orchestrator_main python models/train_model.py --generate-data"
echo ""

# Optionnel: ouvrir l'interface dans le navigateur
if command -v xdg-open &> /dev/null; then
    echo "🌐 Ouverture de l'interface web..."
    sleep 2
    xdg-open http://localhost:8080
elif command -v open &> /dev/null; then
    echo "🌐 Ouverture de l'interface web..."
    sleep 2
    open http://localhost:8080
fi