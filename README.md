# Warehouse Simulator

Proyecto final desarrollado para la cátedra de **Algoritmos y Estructuras de Datos II** de la **Universidad Nacional de Cuyo (UNCUYO)**.

## Descripción

Sistema de gestión y simulación de **Wave Picking** para la preparación eficiente de pedidos en un centro de distribución (*warehouse*).

Permite modelar la estructura física del almacén, organizar pedidos en waves y planificar recorridos para los operarios (*pickers*), utilizando diferentes algoritmos y estrategias de optimización.

## Funcionalidades

- **Modelado del warehouse:** representación espacial mediante grillas y grafos, con racks, pasillos unidireccionales y bidireccionales, puertas y zonas de despacho.
- **Generación automática de escenarios:** creación procedural de un warehouse válido a partir de parámetros mínimos (cantidad de racks, pasillos, productos y su localización, pedidos, máximo de productos por pedido y capacidad de las waves), con ancho/alto configurables, racks verticales, horizontales o mixtos, pasillos sin sentido asignado (AMBOS) y validación de estructura y alcanzabilidad.
- **Generación de waves (Wave Picking):** agrupamiento de pedidos considerando prioridades, ubicaciones, peso y capacidades de carga.
- **Planificación de recorridos (Pathfinding):** cálculo y comparación de rutas para los pickers mediante algoritmos BFS y A*, respetando los sentidos de circulación y evitando colisiones.
- **Simulación interactiva:** visualización del desplazamiento de los pickers, la recolección de productos y el desarrollo de las waves en tiempo real.
- **Comparación de estrategias:** análisis de diferentes alternativas de generación de waves y planificación de recorridos.

## Tecnologías

- **Backend:** Python, Flask.
- **Frontend:** HTML, CSS, JavaScript.
- **Visualización:** Canvas API.
- **Datos:** JSON.

## Demo

Podés acceder a la aplicación y probar la simulación en línea:

[proyecto-final-aed2.vercel.app](https://proyecto-final-aed2.vercel.app/)

## Instalación y ejecución local

### 1. Clonar el repositorio

```bash
git clone https://github.com/gracimarch/proyecto-final-aed2.git
cd proyecto-final-aed2
```

### 2. Crear y activar el entorno virtual

```bash
python -m venv venv
```

**Windows:**
```bash
venv\Scripts\activate
```

**Linux / macOS:**
```bash
source venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Ejecutar la aplicación

```bash
python app.py
```

El servidor se iniciará en `http://127.0.0.1:5000/`. Abrí esa dirección en tu navegador para utilizar el simulador.

## Estructura del proyecto

```text
proyecto-final-aed2/
├── app.py                  # Servidor Flask y endpoints de la API
├── requirements.txt        # Dependencias de Python
├── README.md               # Documentación del proyecto
├── CONSIGNAS.md            # Consignas del proyecto
├── CREDITS.md              # Créditos y atribuciones
├── templates/
│   └── index.html          # Interfaz principal
├── static/
│   ├── css/                # Hojas de estilo
│   ├── js/                 # Lógica del frontend y comunicación con la API
│   │   └── editor/         # Editor del warehouse y simulación
│   ├── images/             # Imágenes estáticas
│   ├── fonts/              # Tipografías e iconografía
│   └── sprites/            # Sprites de cajas y pickers
├── models/                 # Modelos del dominio
│   ├── product.py
│   ├── warehouse.py
│   ├── picker.py
│   ├── order.py
│   ├── wave.py
│   ├── wave_manager.py
│   ├── generator.py
│   ├── simulation.py
│   └── persistence.py      # Validación de escenarios guardados (guardar/cargar)
├── algorithms/             # Algoritmos de grafos y enrutamiento
│   ├── graph.py
│   ├── graph_builder.py
│   ├── pathfinding.py
│   └── routing.py
└── scenarios/              # Escenarios de ejemplo en JSON
    ├── escenario_basico.json
    ├── escenario_grande.json
    └── escenario_grande_v2.json
```
