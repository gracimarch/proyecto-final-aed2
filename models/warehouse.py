from models.product import Product


class Rack:
    """
    Rectángulo de almacenamiento identificado por un id, con posición (x, y),
    ancho y alto en celdas. Uno de los lados (ancho o alto) debe ser 2.

    Cada celda (cx, cy) del rack puede contener productos en distintas alturas z
    (z >= 1). Los slots se indexan por (cx, cy, z).

    Cuando se retira un producto de la posición (cx, cy, z), los productos de
    esa misma celda (cx, cy) en niveles superiores descienden automáticamente.

    Atributos:
        rack_id (str)                      : Identificador del rack.
        x, y    (int)                      : Coordenadas de la esquina inferior izquierda.
        ancho   (int)                      : Extensión sobre el eje x (en celdas).
        alto    (int)                      : Extensión sobre el eje y (en celdas).
        _slots  (dict[tuple, Product])     : Mapa de (cx, cy, z) → Producto.
    """

    def __init__(self, rack_id: str, x: int, y: int, ancho: int, alto: int):
        self.rack_id = rack_id
        self.x = x
        self.y = y
        self.ancho = ancho
        self.alto = alto
        self._slots: dict[tuple, Product] = {}   # (cx, cy, z) -> Product

    @property
    def position(self) -> tuple:
        """Coordenada de la esquina inferior izquierda del rack."""
        return (self.x, self.y)

    @property
    def total_slots(self) -> int:
        """Cantidad total de posiciones ocupadas en el rack."""
        return len(self._slots)

    def contains_cell(self, cx: int, cy: int) -> bool:
        """Devuelve True si la celda (cx, cy) está dentro de este rack."""
        return (self.x <= cx < self.x + self.ancho and
                self.y <= cy < self.y + self.alto)

    def add_product(self, cx: int, cy: int, z: int, product: Product) -> None:
        """
        Ubica un producto en la celda (cx, cy) y nivel z del rack.

        Args:
            cx, cy  : Coordenadas de la celda dentro del rack.
            z       : Nivel vertical (z >= 1).
            product : Producto a ubicar.

        Raises:
            ValueError: Si z < 1, si (cx, cy) no pertenece al rack,
                        o si la posición (cx, cy, z) ya está ocupada.
        """
        if z < 1:
            raise ValueError(f"El nivel z debe ser >= 1: recibido={z}")
        if not self.contains_cell(cx, cy):
            raise ValueError(
                f"La celda ({cx},{cy}) no pertenece al rack '{self.rack_id}'."
            )
        key = (cx, cy, z)
        if key in self._slots:
            raise ValueError(
                f"La posición ({cx},{cy},z={z}) del rack '{self.rack_id}' ya está "
                f"ocupada por el producto '{self._slots[key].product_id}'."
            )
        self._slots[key] = product
        product.location[0] = cx
        product.location[1] = cy
        product.location[2] = z

    def remove_product(self, cx: int, cy: int, z: int) -> Product:
        """
        Retira el producto en (cx, cy, z) y desplaza un nivel hacia abajo
        los productos de la misma celda (cx, cy) que estaban por encima.

        Args:
            cx, cy : Coordenadas de la celda dentro del rack.
            z      : Nivel del producto a retirar.

        Returns:
            El producto retirado.

        Raises:
            KeyError: Si no hay producto en (cx, cy, z).
        """
        key = (cx, cy, z)
        if key not in self._slots:
            raise KeyError(
                f"No hay producto en ({cx},{cy},z={z}) del rack '{self.rack_id}'."
            )
        removed = self._slots.pop(key)

        # Desplazar hacia abajo los productos de la misma celda que estaban por encima
        new_slots: dict[tuple, Product] = {}
        for (kx, ky, kz), slot_product in self._slots.items():
            if kx == cx and ky == cy and kz > z:
                slot_product.drop_z()
                new_slots[(kx, ky, kz - 1)] = slot_product
            else:
                new_slots[(kx, ky, kz)] = slot_product
        self._slots = new_slots

        return removed

    def get_product_at(self, cx: int, cy: int, z: int) -> "Product | None":
        """Retorna el producto en (cx, cy, z), o None si la posición está vacía."""
        return self._slots.get((cx, cy, z))

    def get_all_products(self) -> dict:
        """Retorna una copia del mapa {(cx, cy, z): Product}."""
        return dict(self._slots)

    def is_empty(self) -> bool:
        return len(self._slots) == 0

    def to_dict(self) -> dict:
        """
        Serializa el rack al formato del escenario JSON.

        Solo incluye id, ubicacion, ancho y alto. Los productos
        se serializan por separado en la lista 'productos' del escenario.
        """
        return {
            "id": self.rack_id,
            "ubicacion": {"x": self.x, "y": self.y},
            "ancho": self.ancho,
            "alto": self.alto,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Rack":
        """
        Reconstruye un Rack desde un diccionario en formato de escenario JSON.
        Los productos se agregan externamente vía add_product tras la carga.

        Args:
            data: Diccionario con los campos id, ubicacion, ancho y alto.
        """
        ub = data["ubicacion"]
        return cls(
            rack_id=data["id"],
            x=ub["x"],
            y=ub["y"],
            ancho=data["ancho"],
            alto=data["alto"],
        )

    def __repr__(self) -> str:
        return f"Rack(id={self.rack_id!r}, pos=({self.x},{self.y}), {self.ancho}x{self.alto}, slots={self.total_slots})"


class DispatchZone:
    """
    Zona de despacho: área rectangular donde se consolidan los pedidos
    antes de su envío. Asociada a una puerta específica.

    El picker parte y llega a una celda de pasillo adyacente a esta zona.

    Atributos:
        zone_id     (str)   : Identificador de la zona.
        puerta_id   (str)   : Identificador de la puerta asociada.
        x, y        (int)   : Coordenadas de la esquina inferior izquierda.
        ancho       (int)   : Extensión sobre el eje x (en celdas).
        alto        (int)   : Extensión sobre el eje y (en celdas).
        peso_max_kg (float) : Límite de peso total de los items depositados (kg).
    """

    def __init__(
        self,
        zone_id: str,
        puerta_id: str,
        x: int,
        y: int,
        ancho: int,
        alto: int,
        peso_max_kg: float,
    ):
        self.zone_id = zone_id
        self.puerta_id = puerta_id
        self.x = x
        self.y = y
        self.ancho = ancho
        self.alto = alto
        self.peso_max_kg = peso_max_kg

    def contains_cell(self, cx: int, cy: int) -> bool:
        """Devuelve True si la celda (cx, cy) está dentro de esta zona."""
        return (self.x <= cx < self.x + self.ancho and
                self.y <= cy < self.y + self.alto)

    def to_dict(self) -> dict:
        """
        Serializa la zona de despacho al formato del escenario JSON.
        """
        return {
            "id": self.zone_id,
            "puerta_id": self.puerta_id,
            "ubicacion": {"x": self.x, "y": self.y},
            "ancho": self.ancho,
            "alto": self.alto,
            "peso_max_kg": self.peso_max_kg,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DispatchZone":
        """
        Reconstruye una DispatchZone desde un diccionario en formato de escenario JSON.

        Args:
            data: Diccionario con los campos id, puerta_id, ubicacion,
                  ancho, alto y peso_max_kg.
        """
        ub = data["ubicacion"]
        return cls(
            zone_id=data["id"],
            puerta_id=data["puerta_id"],
            x=ub["x"],
            y=ub["y"],
            ancho=data["ancho"],
            alto=data["alto"],
            peso_max_kg=data["peso_max_kg"],
        )

    def __repr__(self) -> str:
        return (
            f"DispatchZone(id={self.zone_id!r}, puerta={self.puerta_id!r}, "
            f"pos=({self.x},{self.y}), {self.ancho}x{self.alto}, "
            f"peso_max={self.peso_max_kg}kg)"
        )


class Door:
    """
    Puerta (muelle): punto de acceso al warehouse para recepción o expedición,
    ubicada siempre sobre el borde del rectángulo del warehouse.

    Atributos:
        door_id  (str)           : Identificador de la puerta.
        position (tuple[int,int]): Coordenada (x, y) de la puerta sobre el borde.
        tipo     (str)           : 'INBOUND', 'OUTBOUND' o 'AMBOS'.
    """

    VALID_TIPOS = {"INBOUND", "OUTBOUND", "AMBOS"}

    def __init__(self, door_id: str, position: tuple, tipo: str = "AMBOS"):
        if tipo not in self.VALID_TIPOS:
            raise ValueError(f"Tipo inválido '{tipo}'. Opciones: {self.VALID_TIPOS}")
        self.door_id = door_id
        self.position: tuple = tuple(position)
        self.tipo = tipo

    def to_dict(self) -> dict:
        """
        Serializa la puerta al formato del escenario JSON.
        """
        return {
            "id": self.door_id,
            "tipo": self.tipo,
            "ubicacion": {"x": self.position[0], "y": self.position[1]},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Door":
        """
        Reconstruye una Door desde un diccionario en formato de escenario JSON.

        Args:
            data: Diccionario con los campos id, tipo y ubicacion.
        """
        ub = data["ubicacion"]
        return cls(
            door_id=data["id"],
            position=(ub["x"], ub["y"]),
            tipo=data.get("tipo", "AMBOS"),
        )

    def __repr__(self) -> str:
        return f"Door(id={self.door_id!r}, pos={self.position}, tipo={self.tipo!r})"


class Aisle:
    """
    Pasillo: rectángulo con sentido de circulación para los pickers.

    Los pickers se desplazan por celdas de pasillo respetando el sentido
    declarado. Las celdas no declaradas en ningún pasillo tienen sentido AMBOS.

    Atributos:
        aisle_id (str)  : Identificador del pasillo.
        x, y     (int)  : Coordenadas de la esquina inferior izquierda.
        ancho    (int)  : Extensión sobre el eje x (en celdas).
        alto     (int)  : Extensión sobre el eje y (en celdas).
        sentido  (str)  : Dirección de circulación: 'N', 'S', 'E', 'O' o 'AMBOS'.
    """

    VALID_SENTIDOS = {"N", "S", "E", "O", "AMBOS"}

    def __init__(
        self,
        aisle_id: str,
        x: int,
        y: int,
        ancho: int,
        alto: int,
        sentido: str,
    ):
        if sentido not in self.VALID_SENTIDOS:
            raise ValueError(
                f"Sentido inválido '{sentido}'. Opciones: {self.VALID_SENTIDOS}"
            )
        self.aisle_id = aisle_id
        self.x = x
        self.y = y
        self.ancho = ancho
        self.alto = alto
        self.sentido = sentido

    def contains_cell(self, cx: int, cy: int) -> bool:
        """Devuelve True si la celda (cx, cy) pertenece a este pasillo."""
        return (self.x <= cx < self.x + self.ancho and
                self.y <= cy < self.y + self.alto)

    def to_dict(self) -> dict:
        """
        Serializa el pasillo al formato del escenario JSON.
        """
        return {
            "id": self.aisle_id,
            "ubicacion": {"x": self.x, "y": self.y},
            "ancho": self.ancho,
            "alto": self.alto,
            "sentido": self.sentido,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Aisle":
        """
        Reconstruye un Aisle desde un diccionario en formato de escenario JSON.

        Args:
            data: Diccionario con los campos id, ubicacion, ancho, alto y sentido.
        """
        ub = data["ubicacion"]
        return cls(
            aisle_id=data["id"],
            x=ub["x"],
            y=ub["y"],
            ancho=data["ancho"],
            alto=data["alto"],
            sentido=data["sentido"],
        )

    def __repr__(self) -> str:
        return (
            f"Aisle(id={self.aisle_id!r}, pos=({self.x},{self.y}), "
            f"{self.ancho}x{self.alto}, sentido={self.sentido!r})"
        )


class Picker:
    """
    Operario que recorre el warehouse para recolectar los productos de una wave.

    Atributos:
        picker_id          (str)           : Identificador del picker.
        posicion_inicial   (tuple[int,int]): Celda de pasillo de partida (x, y).
        capacidad_carga_kg (float)         : Peso máximo que puede transportar (kg).
    """

    def __init__(
        self,
        picker_id: str,
        posicion_inicial: tuple,
        capacidad_carga_kg: float,
    ):
        if capacidad_carga_kg <= 0:
            raise ValueError(
                f"La capacidad de carga debe ser positiva: {capacidad_carga_kg}"
            )
        self.picker_id = picker_id
        self.posicion_inicial: tuple = tuple(posicion_inicial)
        self.capacidad_carga_kg = capacidad_carga_kg
        self.is_busy: bool = False
        self.assigned_wave_id: str | None = None

    def assign_wave(self, wave_id: str) -> None:
        """Marca al picker como ocupado asignado a una wave."""
        self.is_busy = True
        self.assigned_wave_id = wave_id

    def release(self) -> None:
        """Libera al picker dejándolo disponible."""
        self.is_busy = False
        self.assigned_wave_id = None

    def to_dict(self) -> dict:
        """
        Serializa el picker al formato del escenario JSON.
        """
        return {
            "id": self.picker_id,
            "posicion_inicial": {
                "x": self.posicion_inicial[0],
                "y": self.posicion_inicial[1],
            },
            "capacidad_carga_kg": self.capacidad_carga_kg,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Picker":
        """
        Reconstruye un Picker desde un diccionario en formato de escenario JSON.

        Args:
            data: Diccionario con los campos id, posicion_inicial y capacidad_carga_kg.
        """
        pos = data["posicion_inicial"]
        return cls(
            picker_id=data["id"],
            posicion_inicial=(pos["x"], pos["y"]),
            capacidad_carga_kg=data["capacidad_carga_kg"],
        )

    def __repr__(self) -> str:
        return (
            f"Picker(id={self.picker_id!r}, pos={self.posicion_inicial}, "
            f"cap={self.capacidad_carga_kg}kg)"
        )


class Warehouse:
    """
    Representa el warehouse completo: su estructura física, los elementos
    que lo componen y el catálogo de productos.

    El grafo de navegación (nodos = celdas de pasillo, aristas = movimientos
    válidos según el sentido de circulación) se construye en algorithms/graph.py.

    Atributos:
        warehouse_id    (str)          : Identificador del warehouse.
        ancho_x         (int)          : Ancho en celdas (eje x).
        largo_y         (int)          : Largo en celdas (eje y).
        products        (dict)         : {product_id: Product}
        racks           (dict)         : {rack_id: Rack}
        dispatch_zones  (tuple)        : Zonas de despacho (inmutables tras seal).
        doors           (tuple)        : Puertas (inmutables tras seal).
        aisles          (tuple)        : Pasillos declarados (inmutables tras seal).
        pickers         (tuple)        : Pickers del warehouse (inmutables tras seal).
        wave_max_pedidos  (int)        : Capacidad máxima de pedidos por wave.
        wave_max_productos (int)       : Capacidad máxima de productos por wave.
    """

    def __init__(
        self,
        warehouse_id: str,
        ancho_x: int,
        largo_y: int,
        wave_max_pedidos: int = 5,
        wave_max_productos: int = 20,
    ):
        if ancho_x <= 0 or largo_y <= 0:
            raise ValueError("Las dimensiones del warehouse deben ser positivas.")

        self.warehouse_id = warehouse_id
        self.ancho_x = ancho_x
        self.largo_y = largo_y
        self.wave_max_pedidos = wave_max_pedidos
        self.wave_max_productos = wave_max_productos

        self.products: dict[str, Product] = {}
        self.racks: dict[str, Rack] = {}

        self._dispatch_zones: list[DispatchZone] = []
        self._doors: list[Door] = []
        self._aisles: list[Aisle] = []
        self._pickers: list[Picker] = []
        self._sealed = False

    # ------------------------------------------------------------------
    # Acceso inmutable a componentes fijos
    # ------------------------------------------------------------------

    @property
    def dispatch_zones(self) -> tuple:
        """Zonas de despacho como tupla inmutable."""
        return tuple(self._dispatch_zones)

    @property
    def doors(self) -> tuple:
        """Puertas como tupla inmutable."""
        return tuple(self._doors)

    @property
    def aisles(self) -> tuple:
        """Pasillos declarados como tupla inmutable."""
        return tuple(self._aisles)

    @property
    def pickers(self) -> tuple:
        """Pickers del warehouse como tupla inmutable."""
        return tuple(self._pickers)

    def seal(self) -> None:
        """
        Marca el warehouse como configurado.
        Después de sellar no se pueden agregar zonas, puertas, pasillos ni pickers.
        """
        self._sealed = True

    # ------------------------------------------------------------------
    # Productos
    # ------------------------------------------------------------------

    def add_product(self, product: Product) -> None:
        """
        Registra un producto en el catálogo.

        Raises:
            ValueError: Si ya existe un producto con el mismo id.
        """
        if product.product_id in self.products:
            raise ValueError(f"Ya existe un producto con id '{product.product_id}'.")
        self.products[product.product_id] = product

    def get_product(self, product_id: str) -> Product:
        """
        Retorna el producto con el id indicado.

        Raises:
            KeyError: Si el producto no existe.
        """
        if product_id not in self.products:
            raise KeyError(f"Producto '{product_id}' no encontrado.")
        return self.products[product_id]

    # ------------------------------------------------------------------
    # Racks
    # ------------------------------------------------------------------

    def add_rack(self, rack: Rack) -> None:
        """
        Agrega un rack al warehouse.

        Raises:
            ValueError: Si ya existe un rack con el mismo id o la posición
                        está fuera de los límites del warehouse.
        """
        if rack.rack_id in self.racks:
            raise ValueError(f"Ya existe un rack con id '{rack.rack_id}'.")
        self._validate_position(rack.x, rack.y)
        self.racks[rack.rack_id] = rack

    def get_rack(self, rack_id: str) -> Rack:
        """
        Retorna el rack con el id indicado.

        Raises:
            KeyError: Si el rack no existe.
        """
        if rack_id not in self.racks:
            raise KeyError(f"No hay rack con id '{rack_id}'.")
        return self.racks[rack_id]

    def get_rack_at(self, x: int, y: int) -> "Rack | None":
        """Retorna el rack que contiene la celda (x, y), o None si no hay ninguno."""
        for rack in self.racks.values():
            if rack.contains_cell(x, y):
                return rack
        return None

    # ------------------------------------------------------------------
    # Zonas de despacho
    # ------------------------------------------------------------------

    def add_dispatch_zone(self, zone: DispatchZone) -> None:
        """
        Agrega una zona de despacho al warehouse.

        Raises:
            RuntimeError: Si el warehouse ya fue sellado.
        """
        if self._sealed:
            raise RuntimeError("El warehouse ya fue sellado; no se pueden agregar zonas.")
        self._dispatch_zones.append(zone)

    # ------------------------------------------------------------------
    # Puertas
    # ------------------------------------------------------------------

    def add_door(self, door: Door) -> None:
        """
        Agrega una puerta al warehouse.

        Raises:
            RuntimeError: Si el warehouse ya fue sellado.
        """
        if self._sealed:
            raise RuntimeError("El warehouse ya fue sellado; no se pueden agregar puertas.")
        self._doors.append(door)

    # ------------------------------------------------------------------
    # Pasillos
    # ------------------------------------------------------------------

    def add_aisle(self, aisle: Aisle) -> None:
        """
        Agrega un pasillo declarado al warehouse.

        Raises:
            RuntimeError: Si el warehouse ya fue sellado.
        """
        if self._sealed:
            raise RuntimeError("El warehouse ya fue sellado; no se pueden agregar pasillos.")
        self._aisles.append(aisle)

    def get_aisle_sentido(self, x: int, y: int) -> str:
        """
        Retorna el sentido de circulación de la celda (x, y).
        Si la celda no pertenece a ningún pasillo declarado, retorna 'AMBOS'.
        """
        for aisle in self._aisles:
            if aisle.contains_cell(x, y):
                return aisle.sentido
        return "AMBOS"

    # ------------------------------------------------------------------
    # Pickers
    # ------------------------------------------------------------------

    def add_picker(self, picker: Picker) -> None:
        """
        Agrega un picker al warehouse.

        Raises:
            RuntimeError: Si el warehouse ya fue sellado.
        """
        if self._sealed:
            raise RuntimeError("El warehouse ya fue sellado; no se pueden agregar pickers.")
        self._pickers.append(picker)

    # ------------------------------------------------------------------
    # Validaciones internas
    # ------------------------------------------------------------------

    def _validate_position(self, x: int, y: int) -> None:
        """Lanza ValueError si (x, y) está fuera de los límites del warehouse."""
        if not (0 <= x < self.ancho_x and 0 <= y < self.largo_y):
            raise ValueError(
                f"Posición ({x},{y}) fuera de los límites del warehouse "
                f"({self.ancho_x}x{self.largo_y})."
            )

    def is_valid_position(self, x: int, y: int) -> bool:
        """Devuelve True si (x, y) está dentro de los límites del warehouse."""
        return 0 <= x < self.ancho_x and 0 <= y < self.largo_y

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """
        Serializa el warehouse al formato del escenario JSON.

        Returns:
            Diccionario con las claves warehouse, pickers, productos, pedidos
            y configuracion según la especificación.
        """
        return {
            "warehouse": {
                "dimensiones": {
                    "ancho_x": self.ancho_x,
                    "largo_y": self.largo_y,
                },
                "puertas": [d.to_dict() for d in self._doors],
                "zonas_despacho": [z.to_dict() for z in self._dispatch_zones],
                "racks": [r.to_dict() for r in self.racks.values()],
                "pasillos": [a.to_dict() for a in self._aisles],
            },
            "pickers": [p.to_dict() for p in self._pickers],
            "productos": [p.to_dict() for p in self.products.values()],
            "configuracion": {
                "wave_max_pedidos": self.wave_max_pedidos,
                "wave_max_productos": self.wave_max_productos,
            },
        }

    @classmethod
    def from_dict(cls, data: dict, warehouse_id: str = "warehouse") -> "Warehouse":
        """
        Reconstruye un Warehouse desde un diccionario en formato de escenario JSON.

        Args:
            data         : Diccionario raíz del escenario JSON.
            warehouse_id : Identificador a asignar al warehouse.

        Returns:
            Instancia de Warehouse completamente cargada y sellada.
        """
        wh_data = data["warehouse"]
        dim = wh_data["dimensiones"]
        config = data.get("configuracion", {})

        wh = cls(
            warehouse_id=warehouse_id,
            ancho_x=dim["ancho_x"],
            largo_y=dim["largo_y"],
            wave_max_pedidos=config.get("wave_max_pedidos", 5),
            wave_max_productos=config.get("wave_max_productos", 20),
        )

        # Puertas
        for d_data in wh_data.get("puertas", []):
            wh.add_door(Door.from_dict(d_data))

        # Zonas de despacho
        for z_data in wh_data.get("zonas_despacho", []):
            wh.add_dispatch_zone(DispatchZone.from_dict(z_data))

        # Pasillos
        for a_data in wh_data.get("pasillos", []):
            wh.add_aisle(Aisle.from_dict(a_data))

        # Racks (sin productos aún)
        for r_data in wh_data.get("racks", []):
            wh.add_rack(Rack.from_dict(r_data))

        # Productos: se registran en el catálogo y se ubican en su rack
        for p_data in data.get("productos", []):
            product = Product.from_dict(p_data)
            wh.add_product(product)
            rack = wh.get_rack(product.rack_id)
            rack.add_product(product.x, product.y, product.z, product)

        # Pickers
        for pk_data in data.get("pickers", []):
            wh.add_picker(Picker.from_dict(pk_data))

        wh.seal()
        return wh

    def __repr__(self) -> str:
        return (
            f"Warehouse(id={self.warehouse_id!r}, "
            f"size={self.ancho_x}x{self.largo_y}, "
            f"racks={len(self.racks)}, products={len(self.products)}, "
            f"pickers={len(self._pickers)})"
        )
