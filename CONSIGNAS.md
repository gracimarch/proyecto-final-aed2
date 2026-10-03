# Proyecto Semestral — Algoritmos II

## Título: Sistema de Wave Picking para la preparación de pedidos en un almacén (warehouse)

Equipos de 4 estudiantes

# 1. Objetivos Generales

- Desarrollar una aplicación para simular y gestionar la preparación de pedidos dentro de un Warehouse.
- Modelar la estructura física de un Warehouse usando una estructura de datos vista en clases.
- Implementar algoritmos eficientes para determinar recorridos dentro del Warehouse.
- Desarrollar un sistema de Wave Picking que permita agrupar y procesar pedidos de manera eficiente.
- Implementar mecanismos para determinar recorridos entre las diferentes ubicaciones que deben visitar los operarios.
- Analizar y comparar diferentes algoritmos de resolución en términos de costo temporal y espacial.
- Desarrollar una aplicación visual e interactiva que permita observar el funcionamiento de los algoritmos implementados.

# 2. Introducción

Una empresa de comercio electrónico cuenta con un centro de distribución encargado de almacenar productos y preparar los pedidos realizados por sus clientes.

El Warehouse está compuesto por diferentes pasillos y ubicaciones. Los productos se encuentran distribuidos dentro de dichas ubicaciones.

Durante la jornada se reciben numerosos pedidos. Cada pedido contiene uno o más productos y, por lo tanto, requiere que un operario (picker) recorra diferentes sectores del Warehouse para recolectarlos.

Procesar los pedidos de manera individual puede producir recorridos innecesarios. Por este motivo, la empresa utiliza una estrategia denominada Wave Picking, mediante la cual varios pedidos son agrupados en una misma wave para ser preparados conjuntamente.

Por ejemplo, si dos pedidos contienen productos ubicados en sectores cercanos del Warehouse, puede resultar conveniente procesarlos dentro de la misma wave.

El sistema deberá permitir representar el Warehouse, cargar pedidos y productos, generar waves y determinar los recorridos necesarios para completar cada una de ellas.

El objetivo del proyecto no será encontrar matemáticamente la solución óptima global del problema. En su lugar, los estudiantes deberán diseñar estrategias basadas en algoritmos y estructuras de datos estudiados en la materia y de manera individual.

# 3. Modelo del Warehouse

El Warehouse puede verse como una entidad por si misma por lo que deberá representarse mediante una estructura de datos. Dentro del warehouse encontramos los siguientes elementos:

- Racks: posiciones donde estan guardados los productos. Las posiciones son una tetra <x,y,z> donde <x,y> es la direccion fisica dentro del warehouse y z es la altura a la que se encuentra el producto dentro del rack.
- Zonas de despacho: area donde se preparan, consolidan y organizan los pedidos antes de ser cargados y enviados. Estas zonas estaran representadas por un rectangulo dentro del warehouse, por lo que para ello usaremos como entrada una lista L(<p1,p2>) donde p1 y p2 son posiciones (puntos) dentro del warehouse
- Puertas (muelles): puntos de acceso que conectan el warehouse con el exterior y permiten la recepción (inbound) y/o expedición (outbound) de mercadería.

# 4. Productos

Cada producto deberá poseer como mínimo:

- Identificador único.
- Nombre.
- Ubicación dentro del Warehouse.
- Cantidad disponible.

Ejemplo:

Producto Ubicación Stock

P001 <x,y,z> 20

P002 <x,y,z> 15

P003 <x,y,z> 30

P004 <x,y,z> 10

P005 <x,y,z> 25

Un mismo producto deberá encontrarse en una única ubicación.

# 5. Pedidos

Cada pedido estará compuesto por uno o más productos.

Cada pedido posee los siguientes valores:

- Identificador.
- Lista de productos.
- Cantidad solicitada de cada producto.
- Prioridad. (Valor entero entre 1 a 5 donde a mayor valor mayor prioridad)
- Estado.

Ejemplo:

Pedido P01

P001 × 2

P004 × 1

P005 × 3

Pedido P02

P002 × 1

P003 × 2

Pedido P03

P001 × 1

P003 × 1

P005 × 2

Los pedidos podrán encontrarse en alguno de los siguientes estados: PENDIENTE, EN_WAVE, EN_PREPARACION, PREPARADO

# 6. Waves

Una wave representa un conjunto de pedidos que serán preparados conjuntamente. El sistema deberá permitir crear waves a partir de los pedidos pendientes. Cada wave tendrá una capacidad máxima configurable.

Por ejemplo:

Capacidad máxima de una wave: 3 pedidos

Wave 1: P01, P02, P03

Wave 2: P04, P05

Una wave deberá respetar las restricciones establecidas por el sistema.

Como mínimo deberá considerarse:

- Cantidad máxima de pedidos.
- Cantidad máxima de productos.
- Prioridad de los pedidos.

Los pedidos con mayor prioridad deberán ser considerados antes que los pedidos de menor prioridad.

# 7. Generación de Waves

Los estudiantes deberán implementar un mecanismo para generar waves a partir del conjunto de pedidos pendientes. No será necesario encontrar la partición óptima de los pedidos. En su lugar, deberá implementarse una estrategia algorítmica determinista, claramente definida y justificada.

La estrategia deberá considerar, como mínimo:

- Capacidad de la wave.
- Prioridad de los pedidos.
- Ubicación de los productos.
- Distancia entre las ubicaciones requeridas por los pedidos.

Por ejemplo, una estrategia podría comenzar seleccionando el pedido de mayor prioridad y posteriormente incorporar pedidos que requieran visitar ubicaciones cercanas. Los estudiantes podrán proponer y comparar diferentes estrategias de generación de waves. La estrategia finalmente seleccionada deberá estar justificada desde el punto de vista algorítmico.

# 8. Preparación de una Wave

Una vez creada una wave, el sistema deberá determinar el recorrido necesario para preparar todos sus pedidos.

Supongamos:

Zona de despacho: A

Wave 1:

Pedido P01:

Producto → D

Producto → G

Pedido P02:

Producto → E

Producto → H

El sistema deberá determinar un recorrido que permita visitar las ubicaciones necesarias:

A → D → E → G → H → A

El recorrido deberá realizarse utilizando exclusivamente los pasillos existentes en el Warehouse.

# 9. Estrategias de Recorrido

Cada equipo deberá implementar al menos dos estrategias diferentes para determinar el recorrido de una wave.

Por ejemplo:

### Estrategia A — Orden de los pedidos

Las ubicaciones se visitan siguiendo el orden en que aparecen los pedidos.

### Estrategia B — Cercanía

Luego de visitar una ubicación, se selecciona como siguiente destino una ubicación aún no visitada que se encuentre a menor distancia.

Los equipos podrán proponer otras estrategias siempre que puedan justificarlas algorítmicamente.

Para cada estrategia deberán medir:

- distancia total recorrida;
- cantidad de nodos visitados;
- cantidad de aristas recorridas;
- tiempo de ejecución.

# 10. Comparación de Algoritmos

El sistema deberá permitir comparar las estrategias implementadas. Para una misma wave deberá ser posible ejecutar diferentes algoritmos y observar sus resultados.

Por ejemplo:

Estrategia A Estrategia B

Distancia total 245 198

Puntos visitados 31 27

Tiempo 4 ms 7 ms

Los estudiantes deberán analizar las diferencias obtenidas. La comparación deberá realizarse utilizando diferentes tamaños y configuración de Warehouse y diferentes cantidades de pedidos.

# 11. Aplicación Visual

Uno de los componentes fundamentales del proyecto será la creación de una aplicación visual e interactiva. La aplicación deberá permitir visualizar el Warehouse. Para ello deberán poder visualizarse:

- Pasillos.
- Intersecciones.
- Ubicación de productos.
- Zona de despacho.
- Pedidos.
- Waves.
- Recorrido del picker.

# 12. Simulación Interactiva

La aplicación deberá permitir seleccionar una wave y ejecutar su preparación.

Durante la ejecución deberá poder observarse visualmente cómo el picker (encargado de recoger los productos) se desplaza por el Warehouse.

Por ejemplo:

P01

●

│

│

●──────●──────●

│ │

│ 🚶 │

│ │

●──────●──────●

│

│

📦

DESPACHO

La aplicación deberá permitir:

- iniciar la simulación;
- pausar la simulación;
- continuar la simulación;
- reiniciar la simulación;
- avanzar paso a paso.

Durante la ejecución deberán mostrarse los productos que van siendo recogidos.

La aplicación deberá permitir observar el funcionamiento de los algoritmos propuestos. La visualización deberá permitir comprender cómo trabaja el algoritmo, no solamente mostrar el resultado final.

# 13. Configuración de Escenarios

La aplicación deberá permitir crear o cargar diferentes escenarios de configuración de Warehouse.

Los estudiantes deberán utilizar estos escenarios para analizar el comportamiento de sus algoritmos.

# 16. Generación de escenarios

La aplicación deberá permitir generar Warehouses de manera automática.

La generación deberá permitir configurar, como mínimo:

- cantidad de estantes
- cantidad de pasillos
- cantidad de productos
- localización de los productos
- cantidad de pedidos
- cantidad máxima de productos por pedido
- capacidad de las waves

El sistema deberá garantizar que el Warehouse generado sea válido y que las ubicaciones requeridas puedan ser alcanzadas desde la zona de despacho.

# 17. Persistencia

La configuración del Warehouse, los productos y los pedidos deberá poder guardarse y recuperarse posteriormente.

La aplicación deberá permitir:

Crear escenario

↓

Guardar escenario

↓

Cerrar aplicación

↓

Cargar escenario

↓

Continuar simulación

No deberá ser necesario reconstruir manualmente el escenario cada vez que se inicia la aplicación.

# 18. Requerimientos Técnicos

El proyecto deberá desarrollarse utilizando Python 3.

Se deberá implementar una arquitectura modular que permita separar como mínimo:

Warehouse

↓

Products / Orders

↓

Wave Manager

↓

Pathfinding

↓

Simulation

↓

Visualization

La lógica de los algoritmos deberá estar separada de la interfaz gráfica.

Las estructuras de datos principales utilizadas para representar el problema deberán ser implementadas por el equipo, salvo aquellas bibliotecas expresamente autorizadas por la cátedra.

# 19. Restricciones Algorítmicas

El objetivo del proyecto es aplicar los conocimientos de Algoritmos Avanzados.

Por lo tanto, NO está permitido resolver el problema utilizando:

- programación lineal;
- programación entera;
- solvers de optimización;
- algoritmos genéticos;
- simulated annealing;
- algoritmos evolutivos;
- otras metaheurísticas.

El proyecto puede resolverse utilizando algoritmos y estructuras de datos estudiados durante la materia.

La utilización de algoritmos adicionales deberá ser previamente discutida en las instancias de revision del proyecto.

# 20. Análisis de Complejidad

Para los principales algoritmos implementados deberá analizarse:

- complejidad temporal;
- complejidad espacial;
- mejor caso;
- peor caso;
- comportamiento esperado para diferentes tamaños de entrada.

El análisis deberá estar relacionado con los experimentos realizados.

No será suficiente indicar únicamente la complejidad teórica: deberán presentar evidencia experimental del comportamiento de los algoritmos.

# 21. Experimentación

Cada equipo deberá realizar experimentos utilizando diferentes tamaños de entrada.

Como mínimo deberán analizar:

- tamaño del Warehouse;
- cantidad de pedidos;
- cantidad de productos;
- cantidad de localizaciones;
- cantidad de pasillos.

Para cada escenario deberán registrar:

- tiempo de ejecución;
- distancia recorrida;
- cantidad de elementos procesados;
- cantidad de operaciones relevantes del algoritmo.

Los resultados deberán presentarse mediante tablas y gráficos.

# 22. Preguntas que deberán responder en el informe

El informe final deberá incluir, entre otras, las siguientes preguntas:

- ¿Cómo fue modelado el Warehouse? (estructura de datos)
- ¿Qué representación de la estructura de datos utilizaron y por qué?
- ¿Qué algoritmos utilizaron para resolver los problemas encontrados?
- ¿Por qué eligieron dichos algoritmos?
- ¿Qué ocurre si todos los pasillos tienen el mismo largo?
- ¿Cómo cambia el comportamiento del algoritmo cuando aumenta el tamaño del Warehouse?
- ¿Cómo determinaron la distancia entre las ubicaciones de una wave?
- ¿Cómo decidieron qué pedidos pertenecen a una misma wave?
- ¿Qué estrategia utilizaron para ordenar las ubicaciones de una wave?
- ¿Qué diferencias existen entre las estrategias implementadas?
- ¿Cuál presenta menor distancia recorrida?
- ¿Cuál presenta menor tiempo de ejecución?
- ¿Existe una estrategia que sea mejor en todos los escenarios?
- ¿Qué trade-offs encontraron entre tiempo de ejecución y calidad del recorrido?
- ¿Qué modificaciones realizarían para utilizar el sistema en un Warehouse real?

# 23. Evaluación del Proyecto

La evaluación tendrá en consideración los siguientes factores:

### 1. Comprensión técnica

- Comprensión completa del código por parte de todos los integrantes.
- Capacidad para explicar las decisiones algorítmicas.
- Capacidad para justificar las estructuras de datos utilizadas.

### 2. Funcionamiento

- Correcta representación del Warehouse.
- Correcta generación y procesamiento de pedidos.
- Correcta generación de waves.
- Correcta ejecución de los algoritmos.
- Correcta simulación de los recorridos.

### 3. Algoritmos y estructuras de datos

- Correcta elección de algoritmos.
- Correcta implementación.
- Correcto análisis de complejidad.
- Eficiencia temporal y espacial.

### 4. Aplicación visual

- Claridad de la representación del Warehouse.
- Visualización de los algoritmos.
- Interactividad.
- Calidad de la simulación.
- Facilidad de uso.

### 5. Experimentación

- Calidad de los escenarios utilizados.
- Cantidad y variedad de experimentos.
- Correcta interpretación de resultados.
- Comparación entre algoritmos.

### 6. Calidad del software

- Arquitectura modular.

- Código claro.
- Documentación.
- Manejo de errores.
- Pruebas.

# 24. Entrega

Cada equipo deberá entregar:

- Código fuente completo en repositorio github.
- Repositorio Git con el historial de desarrollo.
- README con instrucciones de instalación y ejecución.
- Documentación técnica.
- Informe de análisis algorítmico.
- Resultados experimentales.
- Escenarios de prueba.
- Presentación oral.

# 25. Demostración Final

Durante la presentación cada equipo deberá realizar una demostración en vivo.

Como mínimo deberá:

- Crear o cargar un Warehouse.
- Mostrar los productos disponibles.
- Crear o cargar pedidos.
- Generar una o más waves.
- Seleccionar una wave.
- Ejecutar los algoritmos.
- Mostrar visualmente los algoritmos.
- Ejecutar el recorrido del picker.
- Mostrar los productos recogidos.
- Comparar al menos dos estrategias.
- Mostrar las métricas obtenidas.

Finalmente, los integrantes deberán responder preguntas sobre las estructuras de datos, algoritmos, complejidad y decisiones de diseño utilizadas.

# 26. Consideración final

El objetivo principal del proyecto no es desarrollar un sistema industrial de optimización de Warehouse.

El objetivo es modelar un problema real mediante estructuras de datos y aplicar algoritmos avanzados para resolver sus diferentes componentes, analizar su eficiencia y construir una aplicación que permita visualizar y comprender el funcionamiento de dichos algoritmos.

La calidad de la solución será evaluada principalmente por la correcta aplicación de los conceptos de Algoritmos Avanzados y por la capacidad de los estudiantes para justificar las decisiones tomadas.
