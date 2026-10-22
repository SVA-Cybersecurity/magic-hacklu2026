SHELL := /bin/bash
COMPOSE := docker compose

ifneq (,$(wildcard .env))
include .env
export
endif

SINGLEUSER_IMAGE ?= magic-workshop-singleuser:latest
SINGLEUSER_BASE_IMAGE ?= quay.io/jupyter/base-notebook:python-3.11
JUPYTERHUB_VERSION ?= 5.3.0
MAGIC_REF ?= main
TIMESKETCH_ADMIN_USER ?= workshop-admin

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk -F':.*?## ' '{printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- setup ------------------------------------------------------------------

.PHONY: bootstrap
bootstrap: ## Create .env, directories and fetch stock Timesketch config
	@./scripts/bootstrap.sh

.PHONY: certs
certs: ## Generate the self-signed TLS certificate
	@./scripts/gen-certs.sh $(FORCE)

.PHONY: htpasswd
htpasswd: ## Enable nginx basic auth (make htpasswd AUTH_USER=name)
	@./scripts/gen-htpasswd.sh "$(AUTH_USER)"

.PHONY: no-htpasswd
no-htpasswd: ## Disable nginx basic auth
	@./scripts/gen-htpasswd.sh --disable

.PHONY: sysctl
sysctl: ## Apply the vm.max_map_count OpenSearch needs (requires sudo)
	sudo sysctl -w vm.max_map_count=262144

# --- images -----------------------------------------------------------------

.PHONY: build
build: build-singleuser ## Build all images
	$(COMPOSE) build

.PHONY: build-singleuser
build-singleuser: ## Build the participant notebook image
	docker build \
		--build-arg SINGLEUSER_BASE_IMAGE=$(SINGLEUSER_BASE_IMAGE) \
		--build-arg JUPYTERHUB_VERSION=$(JUPYTERHUB_VERSION) \
		--build-arg MAGIC_REF=$(MAGIC_REF) \
		-t $(SINGLEUSER_IMAGE) \
		images/singleuser

# --- lifecycle --------------------------------------------------------------

.PHONY: up
up: ## Start the stack
	$(COMPOSE) up -d

.PHONY: down
down: ## Stop the stack (keeps data)
	$(COMPOSE) down

.PHONY: restart
restart: ## Restart the stack
	$(COMPOSE) restart

.PHONY: restart-nginx
restart-nginx: ## Reload nginx after a config change
	$(COMPOSE) restart nginx

.PHONY: restart-hub
restart-hub: ## Restart JupyterHub (stops nothing; notebooks keep running)
	$(COMPOSE) restart jupyterhub

.PHONY: ps
ps: ## Show container status
	$(COMPOSE) ps

.PHONY: logs
logs: ## Tail logs (make logs SVC=jupyterhub)
	$(COMPOSE) logs -f --tail=200 $(SVC)

# --- participants ------------------------------------------------------------

.PHONY: provision
provision: ## Create participants from participants.csv (ARGS="--only alice")
	python3 ./provisioning/provision.py apply $(ARGS)

.PHONY: provision-dry-run
provision-dry-run: ## Show what provisioning would do
	python3 ./provisioning/provision.py apply --dry-run $(ARGS)

.PHONY: deprovision
deprovision: ## Remove participants (ARGS="--only alice")
	python3 ./provisioning/provision.py remove $(ARGS)

.PHONY: jh-users
jh-users: ## List JupyterHub accounts
	$(COMPOSE) exec -T jupyterhub python3 /srv/provisioning/seed_jupyterhub_users.py list

# --- administration ---------------------------------------------------------

.PHONY: ts-admin
ts-admin: ## Create an optional Timesketch admin account for the operator
	$(COMPOSE) exec -T timesketch-web tsctl create-user $(TIMESKETCH_ADMIN_USER) --password '$(TIMESKETCH_ADMIN_PASSWORD)'
	$(COMPOSE) exec -T timesketch-web tsctl make-admin $(TIMESKETCH_ADMIN_USER)

.PHONY: ts-users
ts-users: ## List Timesketch users
	$(COMPOSE) exec timesketch-web tsctl list-users --status

.PHONY: shell-ts
shell-ts: ## Shell into the Timesketch web container
	$(COMPOSE) exec timesketch-web /bin/bash

.PHONY: shell-hub
shell-hub: ## Shell into the JupyterHub container
	$(COMPOSE) exec jupyterhub /bin/bash
