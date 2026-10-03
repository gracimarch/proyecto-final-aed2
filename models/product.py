class Product:
    """
    Representa un producto almacenado en el Warehouse.

    Atributos:
        product_id  (str)        : Identificador único del producto.
        name        (str)        : Nombre descriptivo del producto.
        location    (list[int])  : Posición mutable [x, y, z] dentro del warehouse.
                                   x e y son fijos (posición del rack en el plano).
                                   z puede decrementar cuando un producto debajo es retirado.
        stock       (int)        : Cantidad disponible en esa ubicación.
    """

    def __init__(self, product_id: str, name: str, location: list, stock: int):
        if stock < 0:
            raise ValueError(f"El stock no puede ser negativo: {stock}")
        if len(location) != 3:
            raise ValueError(f"La ubicación debe ser una lista [x, y, z]: {location}")

        self.product_id = product_id
        self.name = name
        self.location: list[int] = list(location)   # [x, y, z] — mutable
        self.stock = stock

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
        Decrementa en 1 la altura z del producto.
        Se llama cuando un producto situado debajo de este es retirado del rack.
        """
        if self.location[2] <= 0:
            raise ValueError(
                f"El producto '{self.product_id}' ya se encuentra en el nivel z=0."
            )
        self.location[2] -= 1

    # ------------------------------------------------------------------
    # Stock
    # ------------------------------------------------------------------

    def reduce_stock(self, quantity: int) -> None:
        """Reduce el stock del producto en la cantidad indicada."""
        if quantity <= 0:
            raise ValueError("La cantidad debe ser positiva.")
        if quantity > self.stock:
            raise ValueError(
                f"Stock insuficiente para '{self.name}': "
                f"disponible={self.stock}, solicitado={quantity}"
            )
        self.stock -= quantity

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serializa el producto a un diccionario (para persistencia JSON)."""
        return {
            "product_id": self.product_id,
            "name": self.name,
            "location": list(self.location),
            "stock": self.stock,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Product":
        """Reconstruye un Product desde un diccionario (carga desde JSON)."""
        return cls(
            product_id=data["product_id"],
            name=data["name"],
            location=list(data["location"]),
            stock=data["stock"],
        )

    def __repr__(self) -> str:
        return (
            f"Product(id={self.product_id!r}, name={self.name!r}, "
            f"location={self.location}, stock={self.stock})"
        )
