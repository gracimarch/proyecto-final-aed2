"""
models/product.py

Un producto guardado en un rack del warehouse (consigna §4).
"""


class Product:
    """
    Representa un producto almacenado en el Warehouse.

    Atributos:
        product_id          (str)   : Identificador único del producto.
        name                (str)   : Nombre descriptivo del producto.
        rack_id             (str)   : Identificador del rack que contiene al producto.
        location            (list)  : Posición [x, y, z] dentro del rack.
                                      x e y son la celda del rack en el plano;
                                      z >= 1 es el nivel (altura) dentro del rack.
        cantidad_disponible (int)   : Stock disponible en esa posición.
        peso_kg             (float) : Peso por unidad, en kilogramos.
    """

    def __init__(self, product_id, name, rack_id, location, cantidad_disponible, peso_kg):
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
        self.location = list(location)   # copia propia: [x, y, z]
        self.cantidad_disponible = cantidad_disponible
        self.peso_kg = peso_kg

    # ------------------------------------------------------------------
    # Acceso a la ubicación
    #
    # @property permite escribir product.x en lugar de product.location[0].
    # Se usa como un atributo (sin paréntesis), pero se calcula al leerlo.
    # ------------------------------------------------------------------

    @property
    def x(self):
        return self.location[0]

    @property
    def y(self):
        return self.location[1]

    @property
    def z(self):
        return self.location[2]

    def drop_z(self):
        """
        Baja el producto un nivel (z - 1). Se usa cuando se retira el
        producto que estaba justo debajo en la misma celda del rack.
        """
        if self.location[2] <= 1:
            raise ValueError(
                f"El producto '{self.product_id}' ya se encuentra en el nivel z=1."
            )
        self.location[2] = self.location[2] - 1

    # ------------------------------------------------------------------
    # Stock
    # ------------------------------------------------------------------

    def reduce_stock(self, quantity):
        """
        Descuenta quantity unidades del stock.

        Raises:
            ValueError: Si la cantidad no es positiva o supera el stock.
        """
        if quantity <= 0:
            raise ValueError("La cantidad debe ser positiva.")
        if quantity > self.cantidad_disponible:
            raise ValueError(
                f"Stock insuficiente para '{self.name}': "
                f"disponible={self.cantidad_disponible}, solicitado={quantity}"
            )
        self.cantidad_disponible = self.cantidad_disponible - quantity

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def to_dict(self):
        """Devuelve el producto como diccionario, en el formato del escenario JSON."""
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
    def from_dict(cls, data):
        """
        Crea un Product a partir de un diccionario del escenario JSON.

        @classmethod significa que se llama sobre la clase, no sobre un
        objeto: Product.from_dict(datos). "cls" es la clase Product.
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

    def __repr__(self):
        # __repr__ define cómo se muestra el objeto al imprimirlo.
        return (
            f"Product(id='{self.product_id}', name='{self.name}', "
            f"rack_id='{self.rack_id}', location={self.location}, "
            f"stock={self.cantidad_disponible}, peso_kg={self.peso_kg})"
        )
