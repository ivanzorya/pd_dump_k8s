#!/bin/bash
docker-compose --file=restore-compose.yml up --build --abort-on-container-exit
