# Getting Started

This section will guide you through the initial setup and basic usage of EchoGTFS.

## Prerequisites
- Docker and Docker Compose
- An existing static GTFS feed

## Installation
1. Clone the repository and enter the directory:
   ```bash
   git clone <repository-url>
   cd echogtfs
   ```
2. Copy and edit the environment configuration:
   ```bash
   cp .env.example .env
   # Edit .env as needed
   ```
3. Start the application:
   ```bash
   docker-compose up -d
   ```
4. Access the web interface at [http://localhost](http://localhost) (or your configured port).

For more details, see the README.md in the project root.
