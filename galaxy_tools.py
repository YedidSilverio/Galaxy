import time

def esperar_finalizacion(gi, job_id, intervalo=10):
    """Espera a que un job de Galaxy finalice."""
    print(f"Esperando finalización del job {job_id}...")
    while True:
        job = gi.jobs.show_job(job_id)
        estado = job.get("state")
        print(f"Estado actual del job {job_id}: {estado}")
        if estado in ["ok", "error"]:
            break
        time.sleep(intervalo)
    return estado

def obtener_historias(gi):
    """Obtiene la lista de historias de Galaxy."""
    # Filtrar los parametros que se requieren
    historias = gi.histories.get_histories(keys=['id', 'name', 'count', 'update_time'])
    return historias

def obtener_datasets_de_historia(gi, history_id):
    """Obtiene los datasets de una historia específica."""
    datasets_raw = gi.histories.show_history(history_id, contents=True)
    datasets = [
        d for d in datasets_raw
        if (not d.get("deleted", False)) and d.get("visible", True) and d.get("state") == "ok"
    ]
    # Filtrar solo FASTQ para FastQC
    datasets_fastq = [
        d for d in datasets 
        if d["name"].lower().endswith((".fastq", ".fq", ".fastq.gz")) or d.get("file_ext") in ["fastqsanger", "fastq"]
    ]
    return datasets_fastq

def ejecutar_fastqc(gi, history_id, datasetID_R1, datasetID_R2=None):
    """
    Ejecuta FastQC en uno o dos datasets.
    Retorna los IDs de los jobs y los outputs.
    """
    
    jobs = []
    tool_id = "toolshed.g2.bx.psu.edu/repos/devteam/fastqc/fastqc/0.72" # ID de la herramienta FastQC (común)
    
    # Ejecutar FastQC para R1
    fastqc_job1 = gi.tools.run_tool(
        history_id=history_id,
        tool_id=tool_id,
        tool_inputs={
                "input_file": {"src": "hda", "id": datasetID_R1}
        }
    )
    jobs.append(fastqc_job1["jobs"][0]["id"])
    
    # Ejecutar FastQC para R2 si se proporciona
    if datasetID_R2 and datasetID_R2 != "":
        fastqc_job2 = gi.tools.run_tool(
            history_id=history_id,
            tool_id=tool_id,
            tool_inputs={
                    "input_file": {"src": "hda", "id": datasetID_R2}
            }
        )
        jobs.append(fastqc_job2["jobs"][0]["id"])

    # Esperar a que todos los jobs finalicen
    for job_id in jobs:
        estado = esperar_finalizacion(gi, job_id)
        if estado == "error":
            print(f"Error en el job {job_id}. Revisar logs de Galaxy.")
            # Se podría lanzar una excepción aquí para que app.py la capture
            
    # Obtener información de los outputs
    results = []
    for job_id in jobs:
        job_info = gi.jobs.show_job(job_id)
        outputs_dict = job_info.get("outputs", {})
        fastqc_outputs = list(outputs_dict.values())
        results.append({
            "job_id": job_id,
            "outputs": fastqc_outputs
        })
        
    return results
import time

def esperar_finalizacion(gi, job_id, intervalo=10):
    """Espera a que un job de Galaxy finalice."""
    print(f"Esperando finalización del job {job_id}...")
    while True:
        job = gi.jobs.show_job(job_id)
        estado = job.get("state")
        print(f"Estado actual del job {job_id}: {estado}")
        if estado in ["ok", "error"]:
            break
        time.sleep(intervalo)
    return estado

def obtener_historias(gi):
    """Obtiene la lista de historias de Galaxy."""
    # Filtrar los parametros que se requieren
    historias = gi.histories.get_histories(keys=['id', 'name', 'count', 'update_time'])
    return historias

def obtener_datasets_de_historia(gi, history_id):
    """Obtiene los datasets de una historia específica."""
    datasets_raw = gi.histories.show_history(history_id, contents=True)
    datasets = [
        d for d in datasets_raw
        if (not d.get("deleted", False)) and d.get("visible", True) and d.get("state") == "ok"
    ]
    # Filtrar solo FASTQ para FastQC
    datasets_fastq = [
        d for d in datasets 
        if d["name"].lower().endswith((".fastq", ".fq", ".fastq.gz")) or d.get("file_ext") in ["fastqsanger", "fastq"]
    ]
    return datasets_fastq

def ejecutar_fastqc(gi, history_id, datasetID_R1, datasetID_R2=None):
    """
    Ejecuta FastQC en uno o dos datasets.
    Retorna los IDs de los jobs y los outputs.
    """
    
    jobs = []
    tool_id = "toolshed.g2.bx.psu.edu/repos/devteam/fastqc/fastqc/0.72" # ID de la herramienta FastQC (común)
    
    # Ejecutar FastQC para R1
    fastqc_job1 = gi.tools.run_tool(
        history_id=history_id,
        tool_id=tool_id,
        tool_inputs={
                "input_file": {"src": "hda", "id": datasetID_R1}
        }
    )
    jobs.append(fastqc_job1["jobs"][0]["id"])
    
    # Ejecutar FastQC para R2 si se proporciona
    if datasetID_R2 and datasetID_R2 != "":
        fastqc_job2 = gi.tools.run_tool(
            history_id=history_id,
            tool_id=tool_id,
            tool_inputs={
                    "input_file": {"src": "hda", "id": datasetID_R2}
            }
        )
        jobs.append(fastqc_job2["jobs"][0]["id"])

    # Esperar a que todos los jobs finalicen
    for job_id in jobs:
        estado = esperar_finalizacion(gi, job_id)
        if estado == "error":
            print(f"Error en el job {job_id}. Revisar logs de Galaxy.")
            # Se podría lanzar una excepción aquí para que app.py la capture
            
    # Obtener información de los outputs
    results = []
    for job_id in jobs:
        job_info = gi.jobs.show_job(job_id)
        outputs_dict = job_info.get("outputs", {})
        fastqc_outputs = list(outputs_dict.values())
        results.append({
            "job_id": job_id,
            "outputs": fastqc_outputs
        })
        
    return results
