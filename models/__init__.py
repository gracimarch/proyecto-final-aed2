# Este archivo marca la carpeta models/ como paquete de Python, para poder
# escribir "from models.order import Order".
#
# Lo dejamos vacío a propósito: si acá importáramos todas las clases, al
# cargar models se cargaría también wave_manager, que a su vez necesita
# algorithms, que a su vez necesita models... y Python se trabaría en un
# import circular. Por eso cada archivo importa directamente lo que usa.
