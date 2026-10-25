"""
models/__init__.py

Junta en un solo lugar todas las clases de la carpeta models/, para poder
importarlas sin nombrar el archivo de cada una:

    from models import Order, Warehouse, WaveManager

Python ejecuta este archivo la primera vez que alguien importa algo de
models, así que estas líneas cargan cada clase y la dejan disponible.
__all__ es la lista de los nombres que la carpeta ofrece hacia afuera.

Si se agrega una clase nueva a models/, hay que sumarla también acá.
(Cuando subamos models/picker.py, Picker pasa a importarse desde ahí.)

Ojo: los archivos que están DENTRO de models/ importan directo del archivo
(from models.order import Order) y no usan este atajo. Si wave.py hiciera
"from models import Order", Python volvería a entrar en este __init__ que
todavía no terminó de cargarse y daría error.
"""

from models.product import Product
from models.order import Order, OrderItem, OrderStatus
from models.wave import Wave, WaveStatus, WaveOrderEntry
from models.warehouse import Warehouse, Rack, DispatchZone, Door, Aisle, Picker
from models.wave_manager import WaveManager

__all__ = [
    "Product",
    "Order",
    "OrderItem",
    "OrderStatus",
    "Wave",
    "WaveStatus",
    "WaveOrderEntry",
    "Picker",
    "Warehouse",
    "Rack",
    "DispatchZone",
    "Door",
    "Aisle",
    "WaveManager",
]
