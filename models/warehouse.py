"""
models/warehouse.py

Estructura física del warehouse (consigna §3): racks, zonas de despacho,
puertas, pasillos y pickers, más el catálogo de productos.

Cada elemento se valida al agregarlo: si no cumple la consigna, se lanza
ValueError con un mensaje que dice qué falló y dónde.
"""

from models.product import Product
from models.picker import Picker


def _capitalize_first(texto: str) -> str:
    """Devuelve el texto con la primera letra en mayúscula ("rack 'R1'" -> "Rack 'R1'")."""
    return texto[:1].upper() + texto[1:]


def _rectangle_cells(x: int, y: int, ancho: int, alto: int) -> list[tuple[int, int]]:
    """Lista de celdas (cx, cy) de un rectángulo, desde (x, y) hasta (x+ancho-1, y+alto-1)."""
    celdas = []
    for dx in range(ancho):
        for dy in range(alto):
            celdas.append((x + dx, y + dy))
    return celdas


class Rack:
    """
    Estantería rectangular. Uno de sus lados (ancho o alto) vale 2, así cada
    celda del rack da a un pasillo (consigna §3.2).

    En cada celda (cx, cy) puede haber productos a distintas alturas z (z >= 1).
    Si se retira un producto, los que estaban arriba en la misma celda bajan
    un nivel.

    Atributos:
        rack_id (str)  : Identificador del rack.
        x, y    (int)  : Esquina inferior izquierda.
        ancho   (int)  : Extensión en x (celdas).
        alto    (int)  : Extensión en y (celdas).
        _slots  (dict) : {(cx, cy, z): Product}
    """

    def __init__(self, rack_id: str, x: int, y: int, ancho: int, alto: int):
        self.rack_id = rack_id
        self.x = x
        self.y = y
        self.ancho = ancho
        self.alto = alto
        self._slots = {}

    @property
    def position(self) -> tuple[int, int]:
        return (self.x, self.y)

    @property
    def total_slots(self) -> int:
        """Cantidad de posiciones ocupadas."""
        return len(self._slots)

    def contains_cell(self, cx: int, cy: int) -> bool:
        """True si la celda (cx, cy) está dentro del rack."""
        dentro_en_x = self.x <= cx < self.x + self.ancho
        dentro_en_y = self.y <= cy < self.y + self.alto
        return dentro_en_x and dentro_en_y

    def add_product(self, cx: int, cy: int, z: int, product: Product) -> None:
        """
        Pone un producto en la celda (cx, cy), nivel z.

        Raises:
            ValueError: Si z < 1, la celda no es del rack o la posición está ocupada.
        """
        if z < 1:
            raise ValueError(f"El nivel z debe ser >= 1: recibido={z}")
        if not self.contains_cell(cx, cy):
            raise ValueError(
                f"La celda ({cx},{cy}) no pertenece al rack '{self.rack_id}'."
            )
        clave = (cx, cy, z)
        if clave in self._slots:
            raise ValueError(
                f"La posición ({cx},{cy},z={z}) del rack '{self.rack_id}' ya está "
                f"ocupada por el producto '{self._slots[clave].product_id}'."
            )
        self._slots[clave] = product
        product.location[0] = cx
        product.location[1] = cy
        product.location[2] = z

    def remove_product(self, cx: int, cy: int, z: int) -> Product:
        """
        Retira el producto de (cx, cy, z) y baja un nivel los que estaban
        encima en la misma celda.

        Raises:
            KeyError: Si no hay producto en esa posición.
        """
        clave = (cx, cy, z)
        if clave not in self._slots:
            raise KeyError(
                f"No hay producto en ({cx},{cy},z={z}) del rack '{self.rack_id}'."
            )
        retirado = self._slots.pop(clave)

        nuevos_slots = {}
        for clave_slot in self._slots:
            producto = self._slots[clave_slot]
            kx = clave_slot[0]
            ky = clave_slot[1]
            kz = clave_slot[2]
            if kx == cx and ky == cy and kz > z:
                producto.drop_z()
                nuevos_slots[(kx, ky, kz - 1)] = producto
            else:
                nuevos_slots[clave_slot] = producto
        self._slots = nuevos_slots
        return retirado

    def get_product_at(self, cx: int, cy: int, z: int) -> Product | None:
        """El producto en (cx, cy, z), o None si está vacío."""
        return self._slots.get((cx, cy, z))

    def get_all_products(self) -> dict[tuple[int, int, int], Product]:
        """Copia del diccionario {(cx, cy, z): Product}."""
        return dict(self._slots)

    def is_empty(self) -> bool:
        return len(self._slots) == 0

    def to_dict(self) -> dict:
        """Solo los datos del rack; los productos se guardan aparte en "productos"."""
        return {
            "id": self.rack_id,
            "ubicacion": {"x": self.x, "y": self.y},
            "ancho": self.ancho,
            "alto": self.alto,
        }

    # El tipo de retorno va entre comillas porque la clase todavía se está
    # definiendo en este punto (Python no la conoce hasta terminar la clase).
    @classmethod
    def from_dict(cls, data: dict) -> "Rack":
        ub = data["ubicacion"]
        return cls(rack_id=data["id"], x=ub["x"], y=ub["y"], ancho=data["ancho"], alto=data["alto"])

    def __repr__(self) -> str:
        return (
            f"Rack(id='{self.rack_id}', pos=({self.x},{self.y}), "
            f"{self.ancho}x{self.alto}, slots={self.total_slots})"
        )


class DispatchZone:
    """
    Zona de despacho: rectángulo frente a una puerta donde se dejan los
    pedidos (consigna §3.4). El recorrido de un picker empieza y termina
    en una celda de pasillo pegada a esta zona.

    Atributos:
        zone_id     (str)   : Identificador.
        puerta_id   (str)   : Puerta asociada.
        x, y        (int)   : Esquina inferior izquierda.
        ancho, alto (int)   : Tamaño en celdas.
        peso_max_kg (float) : Peso máximo que puede haber depositado a la vez.
        peso_actual (float) : Peso depositado ahora.
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
        self.peso_actual = 0.0

    def contains_cell(self, cx: int, cy: int) -> bool:
        dentro_en_x = self.x <= cx < self.x + self.ancho
        dentro_en_y = self.y <= cy < self.y + self.alto
        return dentro_en_x and dentro_en_y

    def has_room_for(self, peso: float) -> bool:
        """True si todavía entran `peso` kg sin pasar el peso máximo."""
        return self.peso_actual + peso <= self.peso_max_kg

    def receive(self, peso: float) -> None:
        """
        Registra peso que deja un picker.

        Raises:
            ValueError: Si la zona pasaría su peso máximo (§3.4).
        """
        if not self.has_room_for(peso):
            raise ValueError(
                f"La zona '{self.zone_id}' superaría su límite: tiene "
                f"{self.peso_actual:.2f} kg, llegan {peso:.2f} kg y el máximo "
                f"es {self.peso_max_kg:.2f} kg."
            )
        self.peso_actual = self.peso_actual + peso

    def to_dict(self) -> dict:
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
            f"DispatchZone(id='{self.zone_id}', puerta='{self.puerta_id}', "
            f"pos=({self.x},{self.y}), {self.ancho}x{self.alto}, "
            f"peso_max={self.peso_max_kg}kg)"
        )


class Door:
    """
    Puerta del warehouse, siempre sobre el borde (consigna §3.3).

    Atributos:
        door_id  (str)   : Identificador.
        position (tuple) : Celda (x, y) de la puerta.
        tipo     (str)   : "INBOUND", "OUTBOUND" o "AMBOS".
    """

    VALID_TIPOS = ["INBOUND", "OUTBOUND", "AMBOS"]

    def __init__(self, door_id: str, position: tuple[int, int], tipo: str = "AMBOS"):
        if tipo not in self.VALID_TIPOS:
            raise ValueError(f"Tipo inválido '{tipo}'. Opciones: {self.VALID_TIPOS}")
        self.door_id = door_id
        self.position = tuple(position)
        self.tipo = tipo

    def to_dict(self) -> dict:
        return {
            "id": self.door_id,
            "tipo": self.tipo,
            "ubicacion": {"x": self.position[0], "y": self.position[1]},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Door":
        ub = data["ubicacion"]
        return cls(door_id=data["id"], position=(ub["x"], ub["y"]), tipo=data.get("tipo", "AMBOS"))

    def __repr__(self) -> str:
        return f"Door(id='{self.door_id}', pos={self.position}, tipo='{self.tipo}')"


class Aisle:
    """
    Pasillo declarado: rectángulo con un sentido de circulación (consigna §3.5).
    Las celdas libres que no están en ningún pasillo declarado tienen sentido AMBOS.

    Atributos:
        aisle_id    (str) : Identificador.
        x, y        (int) : Esquina inferior izquierda.
        ancho, alto (int) : Tamaño en celdas.
        sentido     (str) : "N", "S", "E", "O" o "AMBOS".
    """

    VALID_SENTIDOS = ["N", "S", "E", "O", "AMBOS"]

    def __init__(self, aisle_id: str, x: int, y: int, ancho: int, alto: int, sentido: str):
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
        dentro_en_x = self.x <= cx < self.x + self.ancho
        dentro_en_y = self.y <= cy < self.y + self.alto
        return dentro_en_x and dentro_en_y

    def to_dict(self) -> dict:
        return {
            "id": self.aisle_id,
            "ubicacion": {"x": self.x, "y": self.y},
            "ancho": self.ancho,
            "alto": self.alto,
            "sentido": self.sentido,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Aisle":
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
            f"Aisle(id='{self.aisle_id}', pos=({self.x},{self.y}), "
            f"{self.ancho}x{self.alto}, sentido='{self.sentido}')"
        )


class Warehouse:
    """
    El warehouse completo: dimensiones, elementos físicos y catálogo de productos.

    El grafo para moverse (algorithms/graph_builder.py) se arma a partir de
    este objeto.

    Atributos:
        warehouse_id       (str)  : Identificador.
        ancho_x, largo_y   (int)  : Dimensiones en celdas.
        products           (dict) : {product_id: Product}
        racks              (dict) : {rack_id: Rack}
        dispatch_zones     (tuple): Zonas de despacho.
        doors              (tuple): Puertas.
        aisles             (tuple): Pasillos declarados.
        pickers            (tuple): Pickers.
        wave_max_pedidos   (int)  : Máximo de pedidos por wave.
        wave_max_productos (int)  : Máximo de unidades por wave.

    Cómo se detectan los solapamientos:
        Se guardan tres diccionarios celda -> qué la ocupa:
            _blocking_cells : celdas de racks, puertas y zonas (no se pueden pisar).
            _aisle_cells    : celdas de pasillos declarados.
            _picker_cells   : posiciones iniciales de los pickers.
        Preguntar "¿esta celda está ocupada?" en un diccionario cuesta O(1),
        así que validar un rectángulo cuesta O(celdas del rectángulo).
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

        self.products = {}
        self.racks = {}

        self._dispatch_zones = []
        self._doors = []
        self._aisles = []
        self._pickers = []
        self._sealed = False

        self._blocking_cells = {}   # (x, y) -> "rack 'R1'", "puerta 'D1'", ...
        self._aisle_cells = {}      # (x, y) -> Aisle
        self._picker_cells = {}     # (x, y) -> Picker

    # ------------------------------------------------------------------
    # Listas de elementos
    #
    # Se devuelven como tuplas (que no se pueden modificar) para que nadie
    # agregue elementos sin pasar por las validaciones de add_*.
    # ------------------------------------------------------------------

    @property
    def dispatch_zones(self) -> tuple[DispatchZone, ...]:
        return tuple(self._dispatch_zones)

    @property
    def doors(self) -> tuple[Door, ...]:
        return tuple(self._doors)

    @property
    def aisles(self) -> tuple[Aisle, ...]:
        return tuple(self._aisles)

    @property
    def pickers(self) -> tuple[Picker, ...]:
        return tuple(self._pickers)

    def seal(self) -> None:
        """
        Cierra la configuración: después no se pueden agregar zonas, puertas,
        pasillos ni pickers.

        Raises:
            ValueError: Si alguna puerta no tiene zona de despacho.
        """
        self._validate_every_door_has_zone()
        self._sealed = True

    def _check_not_sealed(self, que: str) -> None:
        if self._sealed:
            raise RuntimeError(f"El warehouse ya fue sellado; no se pueden agregar {que}.")

    # ------------------------------------------------------------------
    # Productos
    # ------------------------------------------------------------------

    def add_product(self, product: Product) -> None:
        """
        Raises:
            ValueError: Si ya existe un producto con ese id.
        """
        if product.product_id in self.products:
            raise ValueError(f"Ya existe un producto con id '{product.product_id}'.")
        self.products[product.product_id] = product

    def get_product(self, product_id: str) -> Product:
        """
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
        Validaciones: id único, un lado vale 2 (§3.2), dentro del warehouse,
        sin solaparse con otro rack, puerta, zona, pasillo ni picker.

        Raises:
            ValueError: Si alguna validación falla.
        """
        label = f"rack '{rack.rack_id}'"
        if rack.rack_id in self.racks:
            raise ValueError(f"Ya existe un rack con id '{rack.rack_id}'.")
        self._validate_rack_has_side_2(rack)
        self._validate_rect_inside(label, rack.x, rack.y, rack.ancho, rack.alto)
        self._validate_rect_free(label, rack.x, rack.y, rack.ancho, rack.alto, False)

        self.racks[rack.rack_id] = rack
        self._mark_blocking(label, rack.x, rack.y, rack.ancho, rack.alto)

    def get_rack(self, rack_id: str) -> Rack:
        """
        Raises:
            KeyError: Si el rack no existe.
        """
        if rack_id not in self.racks:
            raise KeyError(f"No hay rack con id '{rack_id}'.")
        return self.racks[rack_id]

    def get_rack_at(self, x: int, y: int) -> Rack | None:
        """El rack que contiene la celda (x, y), o None."""
        for rack in self.racks.values():
            if rack.contains_cell(x, y):
                return rack
        return None

    # ------------------------------------------------------------------
    # Zonas de despacho
    # ------------------------------------------------------------------

    def add_dispatch_zone(self, zone: DispatchZone) -> None:
        """
        Validaciones: id único, dentro, sin solaparse; su puerta existe, no
        tiene otra zona y la zona queda delante (§3.4). La puerta tiene que
        agregarse antes que la zona.

        Raises:
            RuntimeError: Si el warehouse ya fue sellado.
            ValueError: Si alguna validación falla.
        """
        self._check_not_sealed("zonas")
        label = f"zona de despacho '{zone.zone_id}'"
        for existente in self._dispatch_zones:
            if existente.zone_id == zone.zone_id:
                raise ValueError(f"Ya existe una zona de despacho con id '{zone.zone_id}'.")
        self._validate_rect_inside(label, zone.x, zone.y, zone.ancho, zone.alto)
        self._validate_rect_free(label, zone.x, zone.y, zone.ancho, zone.alto, False)
        self._validate_zone_faces_its_door(zone)

        self._dispatch_zones.append(zone)
        self._mark_blocking(label, zone.x, zone.y, zone.ancho, zone.alto)

    # ------------------------------------------------------------------
    # Puertas
    # ------------------------------------------------------------------

    def add_door(self, door: Door) -> None:
        """
        Validaciones: id único, sobre el borde (§3.3), celda libre.

        Raises:
            RuntimeError: Si el warehouse ya fue sellado.
            ValueError: Si alguna validación falla.
        """
        self._check_not_sealed("puertas")
        label = f"puerta '{door.door_id}'"
        x = door.position[0]
        y = door.position[1]
        for existente in self._doors:
            if existente.door_id == door.door_id:
                raise ValueError(f"Ya existe una puerta con id '{door.door_id}'.")
        self._validate_rect_inside(label, x, y, 1, 1)
        self._validate_door_on_border(door)
        self._validate_rect_free(label, x, y, 1, 1, False)

        self._doors.append(door)
        self._mark_blocking(label, x, y, 1, 1)

    # ------------------------------------------------------------------
    # Pasillos
    # ------------------------------------------------------------------

    def add_aisle(self, aisle: Aisle) -> None:
        """
        Validaciones: id único, dentro, sin solaparse con racks, puertas,
        zonas ni otros pasillos (§3.5). Un picker sí puede estar en un pasillo.

        Raises:
            RuntimeError: Si el warehouse ya fue sellado.
            ValueError: Si alguna validación falla.
        """
        self._check_not_sealed("pasillos")
        label = f"pasillo '{aisle.aisle_id}'"
        for existente in self._aisles:
            if existente.aisle_id == aisle.aisle_id:
                raise ValueError(f"Ya existe un pasillo con id '{aisle.aisle_id}'.")
        self._validate_rect_inside(label, aisle.x, aisle.y, aisle.ancho, aisle.alto)
        self._validate_rect_free(label, aisle.x, aisle.y, aisle.ancho, aisle.alto, True)

        self._aisles.append(aisle)
        for celda in _rectangle_cells(aisle.x, aisle.y, aisle.ancho, aisle.alto):
            self._aisle_cells[celda] = aisle

    def get_aisle_direction(self, x: int, y: int) -> str:
        """Sentido de la celda (x, y); "AMBOS" si no está en ningún pasillo declarado."""
        aisle = self._aisle_cells.get((x, y))
        if aisle is None:
            return "AMBOS"
        return aisle.sentido

    # ------------------------------------------------------------------
    # Pickers
    # ------------------------------------------------------------------

    def add_picker(self, picker: Picker) -> None:
        """
        Validaciones: id único, empieza en una celda de pasillo (§3.6) y no
        hay otro picker en esa celda.

        Raises:
            RuntimeError: Si el warehouse ya fue sellado.
            ValueError: Si alguna validación falla.
        """
        self._check_not_sealed("pickers")
        for existente in self._pickers:
            if existente.picker_id == picker.picker_id:
                raise ValueError(f"Ya existe un picker con id '{picker.picker_id}'.")
        self._validate_picker_on_aisle_cell(picker)

        self._pickers.append(picker)
        self._picker_cells[picker.posicion_inicial] = picker

    # ------------------------------------------------------------------
    # Validaciones
    # ------------------------------------------------------------------

    def is_valid_position(self, x: int, y: int) -> bool:
        """True si (x, y) está dentro del warehouse."""
        return 0 <= x < self.ancho_x and 0 <= y < self.largo_y

    def _validate_position(self, x: int, y: int) -> None:
        if not self.is_valid_position(x, y):
            raise ValueError(
                f"Posición ({x},{y}) fuera de los límites del warehouse "
                f"({self.ancho_x}x{self.largo_y})."
            )

    def _validate_rect_inside(
        self,
        label: str,
        x: int,
        y: int,
        ancho: int,
        alto: int,
    ) -> None:
        """
        El rectángulo tiene tamaño positivo y queda dentro del warehouse.
        Alcanza con revisar dos esquinas opuestas.
        """
        if ancho <= 0 or alto <= 0:
            raise ValueError(
                f"{_capitalize_first(label)} debe tener ancho y alto positivos "
                f"(ancho={ancho}, alto={alto})."
            )
        self._validate_position(x, y)
        self._validate_position(x + ancho - 1, y + alto - 1)

    def _validate_rect_free(
        self,
        label: str,
        x: int,
        y: int,
        ancho: int,
        alto: int,
        allow_pickers: bool,
    ) -> None:
        """
        Ninguna celda del rectángulo está ocupada por un rack, puerta, zona o
        pasillo. Si allow_pickers es False, tampoco puede haber un picker.

        Complejidad: O(ancho × alto), una consulta O(1) por celda.
        """
        for celda in _rectangle_cells(x, y, ancho, alto):
            ocupante = None
            if celda in self._blocking_cells:
                ocupante = self._blocking_cells[celda]
            elif celda in self._aisle_cells:
                ocupante = f"pasillo '{self._aisle_cells[celda].aisle_id}'"
            elif not allow_pickers and celda in self._picker_cells:
                ocupante = f"picker '{self._picker_cells[celda].picker_id}'"

            if ocupante is not None:
                raise ValueError(
                    f"{_capitalize_first(label)} se solapa con {ocupante} en la celda {celda}."
                )

    def _mark_blocking(self, label: str, x: int, y: int, ancho: int, alto: int) -> None:
        """Anota las celdas de un rack, puerta o zona como no transitables."""
        for celda in _rectangle_cells(x, y, ancho, alto):
            self._blocking_cells[celda] = label

    def _validate_rack_has_side_2(self, rack: Rack) -> None:
        """§3.2: uno de los lados del rack vale 2."""
        if rack.ancho != 2 and rack.alto != 2:
            raise ValueError(
                f"El rack '{rack.rack_id}' debe tener un lado igual a 2 "
                f"(ancho={rack.ancho}, alto={rack.alto})."
            )

    def _is_on_border(self, x: int, y: int) -> bool:
        return x == 0 or x == self.ancho_x - 1 or y == 0 or y == self.largo_y - 1

    def _validate_door_on_border(self, door: Door) -> None:
        """§3.3: la puerta está sobre el borde."""
        x = door.position[0]
        y = door.position[1]
        if not self._is_on_border(x, y):
            raise ValueError(
                f"La puerta '{door.door_id}' en ({x},{y}) no está sobre el borde "
                f"del warehouse ({self.ancho_x}x{self.largo_y})."
            )

    def _validate_zone_faces_its_door(self, zone: DispatchZone) -> None:
        """
        §3.4: la puerta de la zona existe, no tiene otra zona, y al menos una
        celda de la zona está pegada a la puerta.
        """
        door = None
        for d in self._doors:
            if d.door_id == zone.puerta_id:
                door = d
                break    # ya la encontramos, no hace falta seguir buscando
        if door is None:
            raise ValueError(
                f"La zona de despacho '{zone.zone_id}' referencia a la puerta "
                f"'{zone.puerta_id}', que no existe."
            )

        for existente in self._dispatch_zones:
            if existente.puerta_id == zone.puerta_id:
                raise ValueError(
                    f"La puerta '{zone.puerta_id}' ya está asignada "
                    f"a la zona '{existente.zone_id}'."
                )

        px = door.position[0]
        py = door.position[1]
        vecinas_de_la_puerta = [(px + 1, py), (px - 1, py), (px, py + 1), (px, py - 1)]
        esta_delante = False
        for celda in vecinas_de_la_puerta:
            if zone.contains_cell(celda[0], celda[1]):
                esta_delante = True
        if not esta_delante:
            raise ValueError(
                f"La zona de despacho '{zone.zone_id}' no está frente a su puerta "
                f"'{door.door_id}' en {door.position}: ninguna celda es adyacente."
            )

    def _validate_picker_on_aisle_cell(self, picker: Picker) -> None:
        """§3.6: el picker empieza en una celda de pasillo y sin otro picker."""
        x = picker.posicion_inicial[0]
        y = picker.posicion_inicial[1]
        self._validate_position(x, y)
        celda = (x, y)
        if celda in self._blocking_cells:
            raise ValueError(
                f"El picker '{picker.picker_id}' empieza en {celda}, que no es pasillo: "
                f"está ocupada por {self._blocking_cells[celda]}."
            )
        if celda in self._picker_cells:
            raise ValueError(
                f"El picker '{picker.picker_id}' empieza en {celda}, donde ya está "
                f"el picker '{self._picker_cells[celda].picker_id}'."
            )

    def _validate_every_door_has_zone(self) -> None:
        """§3.3: frente a cada puerta hay una zona de despacho."""
        puertas_con_zona = set()
        for zona in self._dispatch_zones:
            puertas_con_zona.add(zona.puerta_id)

        faltan = []
        for door in self._doors:
            if door.door_id not in puertas_con_zona:
                faltan.append(door.door_id)

        if len(faltan) > 0:
            raise ValueError(
                f"Las siguientes puertas no tienen zona de despacho: {', '.join(faltan)}."
            )

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """
        El warehouse en el formato del escenario JSON. Los pedidos y las waves
        se guardan con WaveManager.to_dict().
        """
        puertas = []
        for d in self._doors:
            puertas.append(d.to_dict())
        zonas = []
        for z in self._dispatch_zones:
            zonas.append(z.to_dict())
        racks = []
        for r in self.racks.values():
            racks.append(r.to_dict())
        pasillos = []
        for a in self._aisles:
            pasillos.append(a.to_dict())
        pickers = []
        for p in self._pickers:
            pickers.append(p.to_dict())
        productos = []
        for p in self.products.values():
            productos.append(p.to_dict())

        return {
            "warehouse": {
                "dimensiones": {"ancho_x": self.ancho_x, "largo_y": self.largo_y},
                "puertas": puertas,
                "zonas_despacho": zonas,
                "racks": racks,
                "pasillos": pasillos,
            },
            "pickers": pickers,
            "productos": productos,
            "configuracion": {
                "wave_max_pedidos": self.wave_max_pedidos,
                "wave_max_productos": self.wave_max_productos,
            },
        }

    @classmethod
    def from_dict(cls, data: dict, warehouse_id: str = "warehouse") -> "Warehouse":
        """
        Arma el warehouse completo desde el JSON del escenario y lo sella.

        El orden importa: las puertas van antes que las zonas (cada zona
        busca su puerta) y los racks antes que los productos.
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

        for d_data in wh_data.get("puertas", []):
            wh.add_door(Door.from_dict(d_data))
        for z_data in wh_data.get("zonas_despacho", []):
            wh.add_dispatch_zone(DispatchZone.from_dict(z_data))
        for a_data in wh_data.get("pasillos", []):
            wh.add_aisle(Aisle.from_dict(a_data))
        for r_data in wh_data.get("racks", []):
            wh.add_rack(Rack.from_dict(r_data))

        # Cada producto se anota en el catálogo y se pone en su rack.
        for p_data in data.get("productos", []):
            product = Product.from_dict(p_data)
            wh.add_product(product)
            rack = wh.get_rack(product.rack_id)
            rack.add_product(product.x, product.y, product.z, product)

        for pk_data in data.get("pickers", []):
            wh.add_picker(Picker.from_dict(pk_data))

        wh.seal()
        return wh

    def __repr__(self) -> str:
        return (
            f"Warehouse(id='{self.warehouse_id}', size={self.ancho_x}x{self.largo_y}, "
            f"racks={len(self.racks)}, products={len(self.products)}, "
            f"pickers={len(self._pickers)})"
        )
