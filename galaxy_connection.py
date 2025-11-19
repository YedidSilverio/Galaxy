from bioblend.galaxy import GalaxyInstance

# Conecta con Galaxy
gi = GalaxyInstance(
    url="https://usegalaxy.org/",
    key="78eea92c4f450db6101665d6521f37ed"
)

def listar_historiales():
    """Obtiene la lista de historiales del usuario"""
    try:
        return gi.histories.get_histories()
    except Exception as e:
        print(f"Error al listar historiales: {e}")
        return []
