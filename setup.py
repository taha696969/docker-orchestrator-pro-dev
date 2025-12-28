#!/usr/bin/env python3
"""
Script de configuration automatique du système d'orchestration
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

class Colors:
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_step(message):
    print(f"{Colors.BLUE}{Colors.BOLD}[ÉTAPE]{Colors.END} {message}")

def print_success(message):
    print(f"{Colors.GREEN}✓{Colors.END} {message}")

def print_warning(message):
    print(f"{Colors.YELLOW}⚠{Colors.END} {message}")

def print_error(message):
    print(f"{Colors.RED}✗{Colors.END} {message}")

def check_command(command):
    """Vérifier si une commande est disponible"""
    return shutil.which(command) is not None

def run_command(command, capture=False):
    """Exécuter une commande shell"""
    try:
        if capture:
            result = subprocess.run(
                command, shell=True, 
                capture_output=True, 
                text=True, 
                check=True
            )
            return result.stdout.strip()
        else:
            subprocess.run(command, shell=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        return False

def check_prerequisites():
    """Vérifier les prérequis système"""
    print_step("Vérification des prérequis...")
    
    requirements = {
        'docker': 'Docker',
        'docker-compose': 'Docker Compose',
        'python3': 'Python 3'
    }
    
    missing = []
    for cmd, name in requirements.items():
        if check_command(cmd):
            print_success(f"{name} détecté")
        else:
            print_error(f"{name} non trouvé")
            missing.append(name)
    
    if missing:
        print_error(f"Prérequis manquants: {', '.join(missing)}")
        print("\nInstallation:")
        print("  Ubuntu/Debian: sudo apt-get install docker.io docker-compose python3")
        print("  macOS: brew install docker docker-compose")
        return False
    
    return True

def create_directory_structure():
    """Créer la structure de répertoires"""
    print_step("Création de la structure de répertoires...")
    
    directories = [
        'main_container',
        'slave_container',
        'database',
        'models',
        'interface',
        'interface/templates',
        'docker',
        'data',
        'logs'
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print_success(f"Répertoire créé: {directory}")

def create_dockerfile_main():
    """Créer le Dockerfile pour le conteneur principal"""
    print_step("Création du Dockerfile principal...")
    
    dockerfile_content = """FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main_container/ ./main_container/
COPY database/ ./database/
COPY models/ ./models/

EXPOSE 5000

CMD ["python", "main_container/orchestrator.py"]
"""
    
    with open('docker/Dockerfile.main', 'w', encoding='utf-8') as f:
        f.write(dockerfile_content)
    
    print_success("Dockerfile principal créé")

def create_dockerfile_slave():
    """Créer le Dockerfile pour les workers"""
    print_step("Création du Dockerfile worker...")
    
    dockerfile_content = """FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY slave_container/ ./slave_container/

EXPOSE 5001

CMD ["python", "slave_container/worker.py"]
"""
    
    with open('docker/Dockerfile.slave', 'w', encoding='utf-8') as f:
        f.write(dockerfile_content)
    
    print_success("Dockerfile worker créé")

def create_docker_compose():
    """Créer le fichier docker-compose.yml"""
    print_step("Création du docker-compose.yml...")
    
    compose_content = """version: '3.8'

services:
  mongodb:
    image: mongo:6.0
    container_name: orchestrator_mongodb
    ports:
      - "27017:27017"
    volumes:
      - mongodb_data:/data/db
    networks:
      - orchestrator_network
    environment:
      MONGO_INITDB_DATABASE: orchestrator_db

  main:
    build:
      context: .
      dockerfile: docker/Dockerfile.main
    container_name: orchestrator_main
    ports:
      - "5000:5000"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./models:/app/models
      - ./data:/app/data
    networks:
      - orchestrator_network
    depends_on:
      - mongodb
    environment:
      - MONGO_URL=mongodb://mongodb:27017/
      - PYTHONUNBUFFERED=1
    restart: unless-stopped

  web_interface:
    image: nginx:alpine
    container_name: orchestrator_web
    ports:
      - "8080:80"
    volumes:
      - ./interface:/usr/share/nginx/html
    networks:
      - orchestrator_network

networks:
  orchestrator_network:
    driver: bridge

volumes:
  mongodb_data:
"""
    
    with open('docker-compose.yml', 'w', encoding='utf-8') as f:
        f.write(compose_content)
    
    print_success("docker-compose.yml créé")

def create_requirements():
    """Créer le fichier requirements.txt"""
    print_step("Création de requirements.txt...")
    
    requirements = """flask==2.3.3
flask-cors==4.0.0
docker==6.1.3
pymongo==4.5.0
numpy==1.24.3
scikit-learn==1.3.0
joblib==1.3.2
networkx==3.1
matplotlib==3.7.2
psutil==5.9.5
python-dateutil==2.8.2
requests==2.31.0
"""
    
    with open('requirements.txt', 'w', encoding='utf-8') as f:
        f.write(requirements)
    
    print_success("requirements.txt créé")

def create_gitignore():
    """Créer le fichier .gitignore"""
    print_step("Création de .gitignore...")
    
    gitignore_content = """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
*.egg-info/

# Jupyter
.ipynb_checkpoints

# Docker
docker-compose.override.yml

# Data
data/
*.pkl
*.h5
*.model

# Logs
logs/
*.log

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# Models
models/*.pkl
models/*.joblib

# MongoDB
mongodb_data/
"""
    
    with open('.gitignore', 'w', encoding='utf-8') as f:
        f.write(gitignore_content)
    
    print_success(".gitignore créé")

def create_env_file():
    """Créer un fichier .env d'exemple"""
    print_step("Création de .env.example...")
    
    env_content = """# Configuration de l'Orchestrateur
MONGO_URL=mongodb://mongodb:27017/
LOAD_THRESHOLD=80
SCALING_COOLDOWN=60

# Configuration ML
ML_MODEL_PATH=models/predictor_model.pkl
TRAINING_DAYS=7

# Configuration Monitoring
METRICS_INTERVAL=5
METRICS_RETENTION_DAYS=30
"""
    
    with open('.env.example', 'w', encoding='utf-8') as f:
        f.write(env_content)
    
    print_success(".env.example créé")

def create_makefile():
    """Créer un Makefile pour les commandes courantes"""
    print_step("Création de Makefile...")
    
    makefile_content = """# Makefile pour l'Orchestrateur Docker

.PHONY: help build start stop restart logs clean test

help:
\t@echo "Commandes disponibles:"
\t@echo "  make build    - Construire les images Docker"
\t@echo "  make start    - Démarrer le système"
\t@echo "  make stop     - Arrêter le système"
\t@echo "  make restart  - Redémarrer le système"
\t@echo "  make logs     - Voir les logs"
\t@echo "  make clean    - Nettoyer les conteneurs et volumes"
\t@echo "  make test     - Lancer les tests"

build:
\tdocker-compose build

start:
\tdocker-compose up -d
\t@echo "✅ Système démarré!"
\t@echo "Interface: http://localhost:8080"
\t@echo "API: http://localhost:5000"

stop:
\tdocker-compose down

restart:
\tdocker-compose restart

logs:
\tdocker-compose logs -f

clean:
\tdocker-compose down -v
\t@echo "✅ Nettoyage terminé"

test:
\tpython3 examples.py
"""
    
    with open('Makefile', 'w', encoding='utf-8') as f:
        f.write(makefile_content)
    
    print_success("Makefile créé")

def install_python_dependencies():
    """Installer les dépendances Python localement"""
    print_step("Installation des dépendances Python...")
    
    if run_command("pip3 install -r requirements.txt"):
        print_success("Dépendances Python installées")
        return True
    else:
        print_warning("Impossible d'installer les dépendances Python localement")
        print_warning("Elles seront installées dans les conteneurs Docker")
        return True

def create_docker_network():
    """Créer le réseau Docker"""
    print_step("Création du réseau Docker...")
    
    if run_command("docker network create orchestrator_network 2>/dev/null || true"):
        print_success("Réseau Docker créé")
        return True
    return False

def build_docker_images():
    """Construire les images Docker"""
    print_step("Construction des images Docker...")
    
    print("  Construction de l'image orchestrateur...")
    if run_command("docker-compose build main"):
        print_success("Image orchestrateur construite")
    else:
        print_error("Échec de la construction de l'image orchestrateur")
        return False
    
    return True

def main():
    """Fonction principale"""
    print("=" * 70)
    print(f"{Colors.BOLD}🐳 CONFIGURATION DU SYSTÈME D'ORCHESTRATION DOCKER{Colors.END}")
    print("=" * 70)
    print()
    
    # Vérifier les prérequis
    if not check_prerequisites():
        sys.exit(1)
    
    print()
    
    # Créer la structure
    create_directory_structure()
    print()
    
    # Créer les fichiers de configuration
    create_dockerfile_main()
    create_dockerfile_slave()
    create_docker_compose()
    create_requirements()
    create_gitignore()
    create_env_file()
    create_makefile()
    print()
    
    # Installation optionnelle
    print_step("Installation des composants...")
    response = input("Voulez-vous installer les dépendances Python localement? (o/N): ")
    if response.lower() == 'o':
        install_python_dependencies()
    print()
    
    # Créer le réseau Docker
    create_docker_network()
    print()
    
    # Construction des images
    response = input("Voulez-vous construire les images Docker maintenant? (o/N): ")
    if response.lower() == 'o':
        if build_docker_images():
            print_success("Images Docker construites avec succès!")
    print()
    
    # Résumé
    print("=" * 70)
    print(f"{Colors.GREEN}{Colors.BOLD}✅ CONFIGURATION TERMINÉE!{Colors.END}")
    print("=" * 70)
    print()
    print("📝 Prochaines étapes:")
    print("  1. Placez vos fichiers de code dans les répertoires appropriés")
    print("  2. Lancez le système: docker-compose up -d")
    print("  3. Accédez à l'interface: http://localhost:8080")
    print()
    print("💡 Commandes utiles:")
    print("  - make start    : Démarrer le système")
    print("  - make logs     : Voir les logs")
    print("  - make stop     : Arrêter le système")
    print()

if __name__ == "__main__":
    main()