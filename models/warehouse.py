from models.product import Product


class Rack:
    """
    Representa una columna de almacenamiento en el Warehouse, identificada
    por su posición (x, y) en el plano.

    Un rack puede contener múltiples productos distintos en diferentes niveles z.
    El nivel z=0 es el nivel del suelo; z aumenta hacia arriba.

    Cuando un producto es retirado de un nivel z, todos los productos ubicados
    en niveles superiores (z > retirado) descienden un nivel automáticamente
    (simulación de gravedad), actualizando su atributo location[2].

    Atributos:
        x, y    (int)              : Coordenadas del rack en el plano del warehouse.
        _slots  (dict[int, Product]): Mapa de nivel z → Producto.
    """

    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
        self._slots: dict[int, Product] = {}   # z -> Product

    @property
    def position(self) -> tuple:
        """Posición (x, y) del rack en el plano (inmutable)."""
        return (self.x, self.y)

    @property
    def height(self) -> int:
        """Cantidad de niveles ocupados actualmente."""
        return len(self._slots)

    def add_product(self, z: int, product: Product) -> None:
        """
        Ubica un producto en el nivel z del rack.
        Lanza error si el nivel ya está ocupado.
        """
        if z < 0:
            raise ValueError(f"El nivel z debe ser >= 0: recibido={z}")
        if z in self._slots:
            raise ValueError(
                f"El nivel z={z} del rack ({self.x},{self.y}) ya está ocupado "
                f"por el producto '{self._slots[z].product_id}'."
            )
        self._slots[z] = product
        # Sincroniza la ubicación del producto con la posición real en el rack
        product.location[0] = self.x
        product.location[1] = self.y
        product.location[2] = z

    def remove_product(self, z: int) -> Product:
        """
        Retira el producto del nivel z y desplaza hacia abajo los productos
        que estaban por encima (simulación de gravedad).

        Returns:
            El producto retirado.
        """
        if z not in self._slots:
            raise KeyError(
                f"No hay producto en el nivel z={z} del rack ({self.x},{self.y})."
            )
        removed = self._slots.pop(z)

        # Desplazar productos superiores un nivel hacia abajo
        new_slots: dict[int, Product] = {}
        for slot_z, slot_product in self._slots.items():
            if slot_z > z:
                slot_product.drop_z()           # actualiza product.location[2]
                new_slots[slot_z - 1] = slot_product
            else:
                new_slots[slot_z] = slot_product
        self._slots = new_slots

        return removed

    def get_product_at(self, z: int) -> "Product | None":
        """Retorna el producto en el nivel z, o None si está vacío."""
        return self._slots.get(z)

    def get_all_products(self) -> dict:
        """Retorna una copia del mapa {z: Product}."""
        return dict(self._slots)

    def is_empty(self) -> bool:
        return len(self._slots) == 0

    def to_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "slots": {
                str(z): product.product_id
                for z, product in self._slots.items()
            },
        }

    def __repr__(self) -> str:
        products = {z: p.product_id for z, p in self._slots.items()}
        return f"Rack(pos=({self.x},{self.y}), slots={products})"


class DispatchZone:
    """
    Zona de despacho: área rectangular donde se consolidan los pedidos.
    Definida por dos puntos extremos p1=(x1,y1) y p2=(x2,y2).

    Es parte de la especificación del warehouse y no se modifica
    en tiempo de ejecución, por lo que p1 y p2 son tuplas inmutables.

    El punto de entrada/salida del picker es el centroide del rectángulo.
    """

    def __init__(self, zone_id: str, p1: tuple, p2: tuple):
        self.zone_id = zone_id
        self.p1: tuple = tuple(p1)   # inmutable
        self.p2: tuple = tuple(p2)   # inmutable

    @property
    def entry_point(self) -> tuple:
        """Punto central de la zona de despacho (coordenada entera)."""
        cx = (self.p1[0] + self.p2[0]) // 2
        cy = (self.p1[1] + self.p2[1]) // 2
        return (cx, cy)

    def to_dict(self) -> dict:
        return {
            "zone_id": self.zone_id,
            "p1": list(self.p1),
            "p2": list(self.p2),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DispatchZone":
        return cls(
            zone_id=data["zone_id"],
            p1=tuple(data["p1"]),
            p2=tuple(data["p2"]),
        )

    def __repr__(self) -> str:
        return f"DispatchZone(id={self.zone_id!r}, p1={self.p1}, p2={self.p2})"


class Door:
    """
    Puerta (muelle): punto de acceso al warehouse para recepción o expedición.
    Es parte de la especificación del warehouse y no se modifica en tiempo
    de ejecución, por lo que position es una tupla inmutable.

    Atributos:
        door_id  (str)           : Identificador de la puerta.
        position (tuple[int,int]): Coordenada (x, y) de la puerta.
        mode     (str)           : 'inbound', 'outbound' o 'both'.
    """

    VALID_MODES = {"inbound", "outbound", "both"}

    def __init__(self, door_id: str, position: tuple, mode: str = "both"):
        if mode not in self.VALID_MODES:
            raise ValueError(f"Modo inválido '{mode}'. Opciones: {self.VALID_MODES}")
        self.door_id = door_id
        self.position: tuple = tuple(position)   # inmutable
        self.mode = mode

    def to_dict(self) -> dict:
        return {
            "door_id": self.door_id,
            "position": list(self.position),
            "mode": self.mode,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Door":
        return cls(
            door_id=data["door_id"],
            position=tuple(data["position"]),
            mode=data.get("mode", "both"),
        )

    def __repr__(self) -> str:
        return f"Door(id={self.door_id!r}, pos={self.position}, mode={self.mode!r})"


class Warehouse:
    """
    Representa el Warehouse completo.

    El grafo de navegación (nodos = intersecciones, aristas = pasillos)
    se construye y administra en algorithms/graph.py.

    Atributos:
        warehouse_id    (str)               : Nombre o identificador del warehouse.
        width           (int)               : Ancho en unidades (eje x).
        height          (int)               : Alto en unidades (eje y).
        num_pickers     (int)               : Cantidad de pickers disponibles.
        products        (dict)              : {product_id: Product}
        racks           (dict)              : {(x,y): Rack}
        dispatch_zones  (tuple[DispatchZone]): Zonas de despacho (fijas por spec).
        doors           (tuple[Door])       : Puertas/muelles (fijos por spec).
    """

    def __init__(self, warehouse_id: str, width: int, height: int, num_pickers: int = 1):
        if width <= 0 or height <= 0:
            raise ValueError("Las dimensiones del warehouse deben ser positivas.")
        if num_pickers <= 0:
            raise ValueError("La cantidad de pickers debe ser al menos 1.")

        self.warehouse_id = warehouse_id
        self.width = width
        self.height = height
        self.num_pickers = num_pickers

        self.products: dict[str, Product] = {}
        self.racks: dict[tuple, Rack] = {}

        # Zonas y puertas: inmutables una vez cargada la configuración.
        # Se acumulan durante la carga y se sellan con seal().
        self._dispatch_zones: list[DispatchZone] = []
        self._doors: list[Door] = []
        self._sealed = False

    # ------------------------------------------------------------------
    # Acceso inmutable a zonas y puertas
    # ------------------------------------------------------------------

    @property
    def dispatch_zones(self) -> tuple:
        """Zonas de despacho como tupla inmutable."""
        return tuple(self._dispatch_zones)

    @property
    def doors(self) -> tuple:
        """Puertas como tupla inmutable."""
        return tuple(self._doors)

    def seal(self) -> None:
        """
        Marca el warehouse como configurado. Después de sellar,
        no se pueden agregar más zonas de despacho ni puertas.
        """
        self._sealed = True

    # ------------------------------------------------------------------
    # Productos
    # ------------------------------------------------------------------

    def add_product(self, product: Product) -> None:
        """Registra un producto en el catálogo. Lanza error si el id ya existe."""
        if product.product_id in self.products:
            raise ValueError(f"Ya existe un producto con id '{product.product_id}'.")
        self.products[product.product_id] = product

    def get_product(self, product_id: str) -> Product:
        if product_id not in self.products:
            raise KeyError(f"Producto '{product_id}' no encontrado.")
        return self.products[product_id]

    # ------------------------------------------------------------------
    # Racks
    # ------------------------------------------------------------------

    def add_rack(self, rack: Rack) -> None:
        """Agrega un rack en la posición (x, y). No puede haber dos en el mismo lugar."""
        pos = rack.position
        if pos in self.racks:
            raise ValueError(f"Ya existe un rack en la posición {pos}.")
        self._validate_position(pos[0], pos[1])
        self.racks[pos] = rack

    def get_rack(self, x: int, y: int) -> Rack:
        pos = (x, y)
        if pos not in self.racks:
            raise KeyError(f"No hay rack en la posición {pos}.")
        return self.racks[pos]

    # ------------------------------------------------------------------
    # Zonas de despacho
    # ------------------------------------------------------------------

    def add_dispatch_zone(self, zone: DispatchZone) -> None:
        if self._sealed:
            raise RuntimeError("El warehouse ya fue sellado; no se pueden agregar zonas.")
        self._dispatch_zones.append(zone)

    # ------------------------------------------------------------------
    # Puertas
    # ------------------------------------------------------------------

    def add_door(self, door: Door) -> None:
        if self._sealed:
            raise RuntimeError("El warehouse ya fue sellado; no se pueden agregar puertas.")
        self._doors.append(door)

    # ------------------------------------------------------------------
    # Validaciones internas
    # ------------------------------------------------------------------

    def _validate_position(self, x: int, y: int) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError(
                f"Posición ({x},{y}) fuera de los límites del warehouse "
                f"({self.width}x{self.height})."
            )

    def is_valid_position(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "warehouse_id": self.warehouse_id,
            "width": self.width,
            "height": self.height,
            "num_pickers": self.num_pickers,
            "products": {pid: p.to_dict() for pid, p in self.products.items()},
            "racks": {
                f"{pos[0]},{pos[1]}": rack.to_dict()
                for pos, rack in self.racks.items()
            },
            "dispatch_zones": [z.to_dict() for z in self._dispatch_zones],
            "doors": [d.to_dict() for d in self._doors],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Warehouse":
        wh = cls(
            warehouse_id=data["warehouse_id"],
            width=data["width"],
            height=data["height"],
            num_pickers=data.get("num_pickers", 1),
        )

        # Productos
        for p_data in data.get("products", {}).values():
            wh.add_product(Product.from_dict(p_data))

        # Racks y sus productos
        for rack_data in data.get("racks", {}).values():
            rack = Rack(rack_data["x"], rack_data["y"])
            for z_str, pid in rack_data.get("slots", {}).items():
                product = wh.get_product(pid)
                rack.add_product(int(z_str), product)
            wh.add_rack(rack)

        # Zonas de despacho
        for z_data in data.get("dispatch_zones", []):
            wh.add_dispatch_zone(DispatchZone.from_dict(z_data))

        # Puertas
        for d_data in data.get("doors", []):
            wh.add_door(Door.from_dict(d_data))

        wh.seal()
        return wh

    def __repr__(self) -> str:
        return (
            f"Warehouse(id={self.warehouse_id!r}, size={self.width}x{self.height}, "
            f"pickers={self.num_pickers}, products={len(self.products)}, "
            f"racks={len(self.racks)})"
        )
