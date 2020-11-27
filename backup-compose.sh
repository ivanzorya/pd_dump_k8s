#!/bin/bash
docker-compose --file=backup-compose.yml up --build --abort-on-container-exit
