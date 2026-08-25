# Vacio a proposito: su sola presencia en la raiz hace que pytest agregue
# la raiz del proyecto a sys.path, para que los tests puedan hacer
# `from proxy.mecanismos import ...` sin instalar el proyecto como paquete.
