# Sistema de Wave Picking — Warehouse Simulator

Proyecto final desarrollado para la cátedra de **Algoritmos y Estructuras de Datos II** de la **Universidad Nacional de Cuyo (UNCUYO)**.

---

## 📌 Descripción

Este proyecto consiste en el desarrollo y simulación de un sistema de **Wave Picking** para la gestión y preparación eficiente de pedidos dentro de un centro de distribución (*warehouse*).

El sistema permite:
- **Modelar la estructura física del almacén:** representación espacial discreta mediante grilla y grafos (racks, pasillos unidireccionales y bidireccionales, puertas y zonas de despacho).
- **Agrupamiento inteligente de pedidos (Wave Picking):** conformación de *waves* considerando prioridades, ubicaciones, peso y capacidades de carga.
- **Planificación de recorridos (Pathfinding):** cálculo y comparación de rutas óptimas para los operarios (*pickers*) respetando sentidos de circulación y evitando colisiones.
- **Simulación y visualización interactiva:** interfaz gráfica para observar en tiempo real el desplazamiento de los pickers, la recolección de productos y el rendimiento de las distintas estrategias algorítmicas implementadas.

---

## 🌐 Tecnologías

La aplicación está implementada utilizando **Python** y **Flask**, funcionando directamente sobre la web.

Podés acceder y probar la simulación en línea a través del siguiente enlace:  
👉 **[proyecto-final-aed2.vercel.app](https://proyecto-final-aed2.vercel.app)**
