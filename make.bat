@echo off
if "%1"=="" goto up
if "%1"=="up" goto up

echo Unknown target: %1
exit /b 1

:up
docker compose up --build
