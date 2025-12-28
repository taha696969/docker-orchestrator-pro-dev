# Makefile pour l'Orchestrateur Docker

.PHONY: help build start stop restart logs clean test

help:
	@echo "Commandes disponibles:"
	@echo "  make build    - Construire les images Docker"
	@echo "  make start    - Démarrer le système"
	@echo "  make stop     - Arrêter le système"
	@echo "  make restart  - Redémarrer le système"
	@echo "  make logs     - Voir les logs"
	@echo "  make clean    - Nettoyer les conteneurs et volumes"
	@echo "  make test     - Lancer les tests"

build:
	docker-compose build

start:
	docker-compose up -d
	@echo "✅ Système démarré!"
	@echo "Interface: http://localhost:8080"
	@echo "API: http://localhost:5000"

stop:
	docker-compose down

restart:
	docker-compose restart

logs:
	docker-compose logs -f

clean:
	docker-compose down -v
	@echo "✅ Nettoyage terminé"

test:
	python3 examples.py
