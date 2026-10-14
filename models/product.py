class Product:
    """
    Representa un producto almacenado en el Warehouse.

    Atributos:
        product_id          (str)       : Identificador único del producto.
        name                (str)       : Nombre descriptivo del producto.
        rack_id             (str)       : Identificador del rack que contiene al producto.
        location            (list[int]) : Posición mutable [x, y, z] dentro del rack.
                                          x e y son la celda del rack en el plano;
                                          z ≥ 1 es el nivel vertical dentro del rack.
        cantidad_disponible (int)       : Stock disponible en esa posición.
        peso_kg             (float)     : Peso por unidad, en kilogramos.
    """

    def __init__(
        self,
        product_id: str,
        name: str,
        rack_id: str,
        location: list,
        cantidad_disponible: int,
        peso_kg: float,
    ):
        if cantidad_disponible < 0:
            raise ValueError(f"El stock no puede ser negativo: {cantidad_disponible}")
        if len(location) != 3:
            raise ValueError(f"La ubicación debe ser una lista [x, y, z]: {location}")
        if location[2] < 1:
            raise ValueError(f"El nivel z debe ser >= 1: {location[2]}")
        if peso_kg < 0:
            raise ValueError(f"El peso no puede ser negativo: {peso_kg}")

        self.product_id = product_id
        self.name = name
        self.rack_id = rack_id
        self.location: list[int] = list(location)   # [x, y, z] — mutable
        self.cantidad_disponible = cantidad_disponible
        self.peso_kg = peso_kg

    # ------------------------------------------------------------------
    # Propiedades de acceso a la ubicación
    # ------------------------------------------------------------------

    @property
    def x(self) -> int:
        return self.location[0]

    @property
    def y(self) -> int:
        return self.location[1]

    @property
    def z(self) -> int:
        return self.location[2]

    def drop_z(self) -> None:
        """
        Decrementa en 1 el nivel z del producto.
        Se invoca cuando el producto ubicado en el nivel inmediatamente inferior
        es retirado del rack, desplazando este producto un nivel hacia abajo.
        """
        if self.location[2] <= 1:
            raise ValueError(
                f"El producto '{self.product_id}' ya se encuentra en el nivel z=1."
            )
        self.location[2] -= 1

    # ------------------------------------------------------------------
    # Stock
    # ------------------------------------------------------------------

    def reduce_stock(self, quantity: int) -> None:
        """
        Reduce el stock disponible del producto en la cantidad indicada.

        Args:
            quantity: Cantidad a descontar. Debe ser mayor a 0 y no superar
                      el stock disponible actual.

        Raises:
            ValueError: Si la cantidad es inválida o supera el stock disponible.
        """
        if quantity <= 0:
            raise ValueError("La cantidad debe ser positiva.")
        if quantity > self.cantidad_disponible:
            raise ValueError(
                f"Stock insuficiente para '{self.name}': "
                f"disponible={self.cantidad_disponible}, solicitado={quantity}"
            )
        self.cantidad_disponible -= quantity

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """
        Serializa el producto al formato del escenario JSON.

        Returns:
            Diccionario con los campos del producto según la especificación:
            id, nombre, rack_id, ubicacion ({x, y, z}), cantidad_disponible, peso_kg.
        """
        return {
            "id": self.product_id,
            "nombre": self.name,
            "rack_id": self.rack_id,
            "ubicacion": {
                "x": self.location[0],
                "y": self.location[1],
                "z": self.location[2],
            },
            "cantidad_disponible": self.cantidad_disponible,
            "peso_kg": self.peso_kg,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Product":
        """
        Reconstruye un Product desde un diccionario en formato de escenario JSON.

        Args:
            data: Diccionario con los campos id, nombre, rack_id, ubicacion,
                  cantidad_disponible y peso_kg.
        """
        ubicacion = data["ubicacion"]
        return cls(
            product_id=data["id"],
            name=data["nombre"],
            rack_id=data["rack_id"],
            location=[ubicacion["x"], ubicacion["y"], ubicacion["z"]],
            cantidad_disponible=data["cantidad_disponible"],
            peso_kg=data["peso_kg"],
        )

    def __repr__(self) -> str:
        return (
            f"Product(id={self.product_id!r}, name={self.name!r}, "
            f"rack_id={self.rack_id!r}, location={self.location}, "
            f"stock={self.cantidad_disponible}, peso_kg={self.peso_kg})"
        )
