# 🎮 Wordle Multijugador

> ⚠️ **Estado del proyecto: En desarrollo**
>
> Este proyecto se encuentra actualmente en desarrollo activo. Algunas funcionalidades pueden estar incompletas, presentar errores o sufrir cambios importantes en futuras versiones. Se agradece cualquier sugerencia, reporte de fallos o contribución.

## 📖 Descripción

Wordle Multijugador es una aplicación web inspirada en el popular juego Wordle, diseñada para que varios jugadores puedan competir en tiempo real dentro de salas privadas.

Los usuarios pueden crear una sala, compartir un código de acceso con sus amigos y participar en una partida sincronizada mediante WebSockets. El sistema valida las palabras ingresadas utilizando la API de la Real Academia Española (RAE), garantizando que las respuestas sean válidas dentro del idioma español.

## ✨ Características

- 🎯 Juego tipo Wordle.
- 👥 Salas privadas para jugar con amigos.
- 🔗 Invitación mediante código o enlace de sala.
- ⚡ Comunicación en tiempo real mediante WebSockets.
- 🏆 Sistema de clasificación durante la partida.
- 📚 Validación de palabras utilizando la API de la RAE.
- 💾 Persistencia de salas y partidas mediante Redis.
- 🔄 Reconexión automática de jugadores.
- 🚀 Arquitectura preparada para escalar y agregar nuevas funcionalidades.

## 🛠️ Tecnologías utilizadas

### Backend

- Python
- FastAPI
- WebSockets
- Redis

### Frontend

- HTML5
- CSS3
- JavaScript (Vanilla JS)

### Infraestructura

- Docker
- Docker Compose
