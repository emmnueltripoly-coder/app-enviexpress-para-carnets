#!/usr/bin/env bash
# Script de construcción para Render.
# Se ejecuta en cada despliegue antes de iniciar el servidor.
# En caso de error, Render cancela el despliegue y preserva la versión anterior.
set -o errexit

echo "==> Instalando dependencias Python..."
pip install -r requirements.txt

echo "==> Recolectando archivos estáticos (admin Unfold + DRF)..."
python manage.py collectstatic --no-input

echo "==> Aplicando migraciones de base de datos..."
python manage.py migrate --no-input

echo "==> Creando superusuario inicial (idempotente)..."
python manage.py crear_superusuario_inicial

echo "==> Build completado."
