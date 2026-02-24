.DEFAULT_GOAL := help

COMPOSE        = docker compose
NETBOX_COMPOSE = docker compose -f netbox/docker-compose.netbox.yml
DHCP_COMPOSE   = docker compose -f dhcp-integration/docker-compose.yml
ENV_FILE       = ../config/.env

##@ Setup

.PHONY: setup
setup: ## First-time setup: create ../config/.env with auto-generated secrets
	@mkdir -p ../config
	@if [ -f $(ENV_FILE) ]; then \
		echo "⚠  $(ENV_FILE) already exists. Delete it first to regenerate."; \
		exit 1; \
	fi
	@cp .env.example $(ENV_FILE)
	@REDIS_PASS=$$(openssl rand -base64 32 | tr -dc 'A-Za-z0-9' | head -c 40); \
	 sed -i.bak "s/REDIS_PASSWORD=.*/REDIS_PASSWORD=$$REDIS_PASS/" $(ENV_FILE) && rm -f $(ENV_FILE).bak; \
	 echo "✓ Generated Redis password"
	@echo ""
	@echo "✓ Created $(ENV_FILE) from .env.example"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Edit $(ENV_FILE) and fill in NETBOX_TOKEN, ILO_DEFAULT_PASSWORD, CALLBACK_API_URL"
	@echo "  2. Run: make netbox-up   (start NetBox)"
	@echo "  3. Run: make netbox-init (populate infrastructure data)"
	@echo "  4. Run: make up          (start all workers)"

##@ NetBox

.PHONY: netbox-up
netbox-up: ## Start NetBox stack (Postgres, Redis, NetBox)
	$(NETBOX_COMPOSE) --env-file $(ENV_FILE) up -d
	@echo "✓ NetBox starting at http://localhost:8000"
	@echo "  Waiting for NetBox to be ready..."
	@$(NETBOX_COMPOSE) --env-file $(ENV_FILE) exec netbox bash -c \
	  'for i in $$(seq 1 30); do curl -sf http://localhost:8080/api/ > /dev/null 2>&1 && echo "✓ NetBox ready" && exit 0; sleep 2; done; echo "✗ NetBox did not start in time"; exit 1' \
	  2>/dev/null || echo "  Run 'make netbox-logs' to check status"

.PHONY: netbox-down
netbox-down: ## Stop NetBox stack
	$(NETBOX_COMPOSE) --env-file $(ENV_FILE) down

.PHONY: netbox-logs
netbox-logs: ## Tail NetBox logs
	$(NETBOX_COMPOSE) --env-file $(ENV_FILE) logs -f

.PHONY: netbox-init
netbox-init: ## Populate NetBox with infrastructure data (sites, racks, devices)
	@echo "Running NetBox infrastructure initialization..."
	@if [ -f netbox-init/create_infrastructure_final.py ]; then \
	  source $(ENV_FILE) 2>/dev/null; \
	  python3 netbox-init/create_infrastructure_final.py; \
	else \
	  echo "✗ netbox-init/create_infrastructure_final.py not found"; \
	fi

##@ Workers

.PHONY: up
up: check-env ## Start all worker services + Redis (all-in-one mode)
	$(COMPOSE) --env-file $(ENV_FILE) --profile all-in-one up -d --build
	@echo "✓ Workers started"
	@echo "  Callback API: http://localhost:5000"

.PHONY: up-separate
up-separate: check-env ## Start workers as separate containers
	$(COMPOSE) --env-file $(ENV_FILE) --profile separate up -d --build

.PHONY: down
down: ## Stop all worker services
	$(COMPOSE) --env-file $(ENV_FILE) --profile all-in-one --profile separate down

.PHONY: restart
restart: down up ## Restart all worker services

.PHONY: logs
logs: ## Tail worker logs
	$(COMPOSE) --env-file $(ENV_FILE) --profile all-in-one logs -f

.PHONY: status
status: ## Show status of all containers
	@echo "=== Workers ==="
	@$(COMPOSE) --env-file $(ENV_FILE) --profile all-in-one --profile separate ps 2>/dev/null || true
	@echo ""
	@echo "=== NetBox ==="
	@$(NETBOX_COMPOSE) --env-file $(ENV_FILE) ps 2>/dev/null || true
	@echo ""
	@echo "=== DHCP Integration ==="
	@$(DHCP_COMPOSE) --env-file $(ENV_FILE) ps 2>/dev/null || true

##@ DHCP Integration

.PHONY: dhcp-up
dhcp-up: check-env ## Start DHCP integration stack (BMC worker + Redis for remote DHCP server)
	$(DHCP_COMPOSE) --env-file $(ENV_FILE) up -d --build
	@echo "✓ DHCP integration started"
	@echo "  Redis port 6380 is open for the DHCP server hook"
	@echo "  Configure your DHCP server with REDIS_HOST=<this-host> REDIS_PORT=6380"
	@grep REDIS_PASSWORD $(ENV_FILE) | head -1

.PHONY: dhcp-down
dhcp-down: ## Stop DHCP integration stack
	$(DHCP_COMPOSE) --env-file $(ENV_FILE) down

.PHONY: dhcp-logs
dhcp-logs: ## Tail DHCP integration logs
	$(DHCP_COMPOSE) --env-file $(ENV_FILE) logs -f

.PHONY: dhcp-test
dhcp-test: ## Simulate a BMC DHCP discovery event (usage: make dhcp-test MAC=A0:36:9F:01:00:00 IP=10.0.100.50)
	@MAC=$(MAC); IP=$(IP); \
	[ -z "$$MAC" ] && MAC="A0:36:9F:01:00:00"; \
	[ -z "$$IP" ] && IP="10.0.100.50"; \
	echo "Simulating BMC discovery: MAC=$$MAC IP=$$IP"; \
	cd dhcp-integration && ./test-bmc-discovery.sh $$MAC $$IP

##@ Portal

.PHONY: portal-up
portal-up: check-env ## Start chatbot portal (port 8080)
	$(COMPOSE) --env-file $(ENV_FILE) up -d --build portal
	@echo "✓ Portal starting at http://localhost:8080"

.PHONY: portal-down
portal-down: ## Stop chatbot portal
	$(COMPOSE) --env-file $(ENV_FILE) stop portal

.PHONY: portal-logs
portal-logs: ## Tail portal chatbot logs
	$(COMPOSE) --env-file $(ENV_FILE) logs -f portal

.PHONY: portal-open
portal-open: ## Open portal in browser
	@open http://localhost:8080 2>/dev/null || xdg-open http://localhost:8080 2>/dev/null || echo "Open http://localhost:8080 in your browser"

##@ Maintenance

.PHONY: reset
reset: ## ⚠ Stop everything and delete all volumes (DESTRUCTIVE)
	@echo "⚠  This will destroy all data in Redis and NetBox volumes."
	@read -p "Are you sure? [y/N] " ans && [ "$$ans" = "y" ]
	$(COMPOSE) --env-file $(ENV_FILE) --profile all-in-one --profile separate down -v
	$(NETBOX_COMPOSE) --env-file $(ENV_FILE) down -v
	$(DHCP_COMPOSE) --env-file $(ENV_FILE) down -v
	@echo "✓ All volumes removed"

.PHONY: redis-cli
redis-cli: ## Open a Redis CLI shell (authenticated)
	@PASSWORD=$$(grep REDIS_PASSWORD $(ENV_FILE) | cut -d= -f2); \
	docker exec -it bm-redis redis-cli -a "$$PASSWORD"

.PHONY: check-env
check-env:
	@if [ ! -f $(ENV_FILE) ]; then \
	  echo "✗ $(ENV_FILE) not found. Run 'make setup' first."; \
	  exit 1; \
	fi
	@if grep -q "your-netbox-api-token-here\|your-ilo-password-here\|your-anthropic-api-key-here" $(ENV_FILE) 2>/dev/null; then \
	  echo "✗ $(ENV_FILE) has unfilled placeholders. Edit it before running."; \
	  exit 1; \
	fi

##@ Help

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} \
	  /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 } \
	  /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' $(MAKEFILE_LIST)
