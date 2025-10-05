from flask import Flask, render_template, request, make_response, send_file, jsonify, Response, url_for
import pandas as pd
import sqlite3
import pickle
import networkx as nx
import matplotlib
import pickle
import csv
import io
import unicodedata
import re
import os
from pyvis.network import Network
import base64
matplotlib.use('Agg')



app = Flask(__name__)

with open('graph_mecai_8.pkl', 'rb') as file:
    G = pickle.load(file)

# Control variables
visualization_history = []  # Store node's states
current_viz_index = 0       # Current viz index
explored_nodes = set()

previous_clicked_node = None
current_clicked_node = None

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/user_input_analysis', methods=['GET', 'POST'])
def user_input_analysis():
    """Main route for graph visualization."""
    global current_viz_index, visualization_history, explored_nodes

    graph_html = None
    error_message = None

    if request.method == 'POST':
        action_node = request.form.get('action')

        if action_node == 'caminho_grafo':
            start_node_name = request.form['start_node_name']
            node_type = request.form.get('node_type')  # Will be 'PF' or 'PJ'
            
            if node_type == 'PF':
                cpf = request.form.get('cpf', '').replace('.', '').replace('-', '')
                is_complete = request.form.get('cpf_type') == 'complete'
                document = cpf[3:9] if is_complete else cpf
            else:  # PJ
                cnpj = request.form.get('cnpj', '').replace('.', '').replace('-', '').replace('/', '')
                is_complete = request.form.get('cnpj_type') == 'complete'
                document = cnpj[3:9] if is_complete else cnpj

            start_node = f"{node_type}_{document}_{removerAcentosECaracteresEspeciais(start_node_name)}"

            if not start_node_name:
                error_message = "Por favor, forneça um nome."
            elif not node_type:
                error_message = "Por favor, selecione se é Pessoa Física ou Jurídica."
            elif (node_type == 'PF' and not cpf) or (node_type == 'PJ' and not cnpj):
                error_message = f"Por favor, forneça um {'CPF' if node_type == 'PF' else 'CNPJ'} válido."
            elif start_node not in G:
                error_message = f"Pessoa/Empresa '{start_node_name}' não foi encontrada no relacionamento!"
            else:
                explored_nodes.add(start_node)
                visualization_history.append({
                    "center_node": start_node,
                    "explored_nodes": set(explored_nodes),
                    "node_colors": {}
                })
                current_viz_index = len(visualization_history) - 1

    if visualization_history and not error_message:
        current_viz = visualization_history[current_viz_index]
        graph_html = generate_graph(
            G,
            current_viz["center_node"],
            current_viz["explored_nodes"],
            current_viz["node_colors"]
        )

    return render_template("user_input_analysis.html", graph_html=graph_html or "", error_message=error_message)

@app.route('/expand', methods=['POST'])
def expand():
    """Route to expand the graph by clicking a node."""
    global visualization_history, current_viz_index, previous_clicked_node, current_clicked_node

    data = request.json
    clicked_node = data.get("node")

    # Define restricted nodes that should not expand
    RESTRICTED_NODES = {"PEP", "BOLSA_FAM", "AUX_EMER"}  # Exact node names

    if clicked_node not in G:
        return jsonify({"error": f"Pessoa/Empresa '{clicked_node}' não foi encontrada no relacionamento!"}), 400

    # Prevent expansion for restricted nodes
    if clicked_node in RESTRICTED_NODES:
        return jsonify({
            "status": "success",
            "message": f"Nó restrito '{clicked_node}' não pode ser expandido."
        })

    # Proceed only for non-restricted nodes
    previous_clicked_node = current_clicked_node
    current_clicked_node = clicked_node
    explored_nodes.add(clicked_node)

    current_viz = visualization_history[current_viz_index]
    new_viz = {
        "center_node": clicked_node,
        "explored_nodes": set(explored_nodes),
        "node_colors": current_viz["node_colors"].copy()
    }

    visualization_history = visualization_history[:current_viz_index + 1]
    visualization_history.append(new_viz)
    current_viz_index += 1

    return jsonify({"status": "success", "message": f"Expanded node: {clicked_node}"})

@app.route('/navigate', methods=['POST'])
def navigate():
    """API to navigate between visualizations."""
    global current_viz_index, visualization_history

    direction = request.json.get("direction")
    if direction == "previous" and current_viz_index > 0:
        current_viz_index -= 1
        return jsonify({"status": "success", "message": "Navegado para a visualização anterior."})
    elif direction == "next" and current_viz_index < len(visualization_history) - 1:
        current_viz_index += 1
        return jsonify({"status": "success", "message": "Navegado para a próxima visualização."})
    else:
        return jsonify({"status": "error", "message": "Não é possível navegar mais nesta direção."})

@app.route('/download')
def download_graph():
    """Route to download the graph as an HTML file."""
    global visualization_history, current_viz_index

    current_viz = visualization_history[current_viz_index]
    html_content = generate_graph(G, current_viz["center_node"], current_viz["explored_nodes"], current_viz["node_colors"])

    filename = "graph_visualization.html"
    return Response(
        html_content,
        mimetype='text/html',
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )

def encode_image_to_base64(image_path):
    """Encode an image file to base64."""
    with open(image_path, "rb") as img_file:
        img_data = img_file.read()
        return base64.b64encode(img_data).decode('utf-8')

def generate_graph(graph, center_node, explored_nodes, node_colors):
    global previous_clicked_node, current_clicked_node

    explored_nodes.add(center_node)
    subgraph_nodes = set()
    for node in explored_nodes:
        subgraph_nodes.update(nx.single_source_shortest_path_length(graph, node, cutoff=1).keys())

    subgraph = graph.subgraph(subgraph_nodes)
    net = Network(height="750px", width="100%", directed=True, notebook=False)

    for node in subgraph.nodes:
        if node in ['BOLSA_FAM', 'AUX_EMER']:
            color = "red"
        elif node == current_clicked_node:
            color = "darkgreen"
        elif node == previous_clicked_node:
            color = "orange"
        elif current_clicked_node and node in graph[current_clicked_node]:
            color = "lightgreen"
        else:
            color = "blue"

        node_colors[node] = color

        # Assign node image based on the first two characters (PF or PJ)
        if node[:2] == "PF":
            image_path = f"static/images/user_{color}.png"
        elif node[:2] == "PJ":
            image_path = f"static/images/enterprise_{color}.png"
        elif node[:3] == "PEP":
            image_path = f"static/images/PEP.png"
        elif node[:3] == "BOL" or "AUX":
            image_path = f"static/images/money_{color}.png"
        else:
            image_path = f"static/images/enterprise_{color}.png"

        # Convert image to base64 and embed it
        img_base64 = encode_image_to_base64(image_path)
        net.add_node(node, shape="image", image=f"data:image/png;base64,{img_base64}", label=node, color=color)

    for edge in subgraph.edges:
        source, target = edge
        edge_type = subgraph.edges[edge].get("tipo", "undefined")
        net.add_edge(source, target, title=edge_type, arrows="to")

    net.toggle_physics(True)
    html = net.generate_html()

    # Add the legend to the generated HTML
    legend_html = """
    <style>
        .legend {
            position: absolute;
            top: 10px;
            right: 10px;
            background: white;
            padding: 10px;
            border-radius: 5px;
            border: 1px solid #ccc;
            box-shadow: 0px 0px 10px rgba(0, 0, 0, 0.1);
            font-size: 14px;
            z-index: 1000;
        }
        .legend div {
            display: flex;
            align-items: center;
            margin-bottom: 5px;
        }
        .legend .color-box {
            width: 20px;
            height: 20px;
            margin-right: 10px;
        }
    </style>
    <div class="legend">
        <div>
            <div class="color-box" style="background-color: #FFA500;"></div>
            <span>Último Nó clicado</span>
        </div>
        <div>
            <div class="color-box" style="background-color: #0000FF;"></div>
            <span>Nó ainda não clicado</span>
        </div>
        <div>
            <div class="color-box" style="background-color: #006400;"></div>
            <span>Nó atualmente clicado</span>
        </div>
        <div>
            <div class="color-box" style="background-color: #90EE90;"></div>
            <span>Nós diretamente relacionados o Nó clicado</span>
        </div>
        <div>
            <div class="color-box" style="background-color: #E3464C;"></div>
            <span>Auxílio Emergencial ou Bolsa Família</span>
        </div>
        <div>
            <div class="color-box" style="background-color: #DD6629;"></div>
            <span>PEP</span>
        </div>
    </div>
    """

    # Insert the legend into the generated HTML
    html = html.replace("</body>", legend_html + "</body>")
    return enhance_html_with_js(html)

def enhance_html_with_js(html):
    """Enhance HTML with JavaScript for interactions and fixed download button."""
    js_snippet = """
    <style>
        :root {
            --primary-blue: #002147;
            --secondary-blue: #004080;
            --accent-green: #4CAF50;
            --light-gray: #f5f7fa;
            --medium-gray: #e0e7ff;
            --dark-gray: #4a5568;
        }

        /* Fixed button container specific styles */
        .button-container {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            display: flex;
            gap: 10px;
            z-index: 9999;
            background: rgba(255, 255, 255, 0.9); /* Subtle background for the container */
            padding: 15px 30px; /* Adjusted padding to give more space */
            border-radius: 12px; /* Slightly more rounded corners for the container */
            box-shadow: 0 6px 20px rgba(0,0,0,0.2); /* Enhanced shadow for prominence */
            backdrop-filter: blur(6px); /* Stronger blur effect */
            transition: opacity 0.3s ease, transform 0.3s ease;
            animation: fadeInUp 0.5s ease-out forwards; /* Keep animation for initial load */
        }
        
        /* General button styles for consistency, reused from descriptive_analysis.html */
        .btn-primary {
            padding: 12px 25px; /* Adjust padding for the button */
            font-size: 1em;
            border-radius: 50px; /* More rounded button */
            background: linear-gradient(135deg, var(--primary-blue), var(--secondary-blue));
            box-shadow: 0 4px 15px rgba(0, 33, 71, 0.2);
            transition: all 0.3s ease;
            text-decoration: none; /* Ensure it's a link */
            display: inline-flex;
            align-items: center;
            gap: 8px; /* Gap for icon */
            color: white; /* Ensure text color is white */
            border: none; /* Remove default border */
        }
        .btn-primary:hover {
            background: linear-gradient(135deg, var(--secondary-blue), var(--accent-green));
            transform: translateY(-3px);
            box-shadow: 0 6px 20px rgba(0, 33, 71, 0.3);
        }
        
        /* Icon within the button, if you want specific icon sizing */
        .btn-primary svg {
            font-size: 1.1em; /* Adjust icon size if needed */
        }

        /* Animation for scroll appearance */
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(30px) translateX(-50%); }
            to { opacity: 1; transform: translateY(0) translateX(-50%); }
        }
        
        /* Hide animation when hidden by scroll */
        .button-container.hidden {
            opacity: 0;
            transform: translateY(20px) translateX(-50%);
            pointer-events: none; /* Disable interaction when hidden */
        }
    </style>
    
    <script type="text/javascript">
        // Existing network and navigation code remains unchanged
        // Assuming 'network' is defined elsewhere for vis.js graph
        if (typeof network !== 'undefined') {
            network.on("click", function (params) {
                if (params.nodes.length > 0) {
                    let clickedNode = params.nodes[0];
                    fetch("/expand", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ node: clickedNode })
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === "success") {
                            window.location.reload();
                        } else {
                            alert(data.error || "Ocorreu um erro.");
                        }
                    });
                }
            });
        } else {
            console.warn("Vis.js network object not found. Ensure it's initialized before this script.");
        }


        function navigate(direction) {
            fetch("/navigate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ direction: direction })
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === "success") {
                    window.location.reload();
                } else {
                    alert(data.message || "Erro de navegação.");
                }
            });
        }
        
        // Scroll-based button enhancement
        document.addEventListener('DOMContentLoaded', function() {
            const btnContainer = document.querySelector('.button-container');
            if (btnContainer) { // Check if the container exists
                const toggleVisibility = () => {
                    if (window.scrollY > 100) {
                        btnContainer.classList.remove('hidden');
                    } else {
                        btnContainer.classList.add('hidden');
                    }
                };

                window.addEventListener('scroll', toggleVisibility);
                
                // Initialize button state on load
                toggleVisibility(); 
            }
        });
    </script>
    
    <div class="button-container">
        <a href="/download" class="btn-primary">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
                <path d="M.5 9.9a.5.5 0 0 1 .5.5v2.5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-2.5a.5.5 0 0 1 1 0v2.5a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2v-2.5a.5.5 0 0 1 .5-.5z"/>
                <path d="M7.646 11.854a.5.5 0 0 0 .708 0l3-3a.5.5 0 0 0-.708-.708L8.5 10.293V1.5a.5.5 0 0 0-1 0v8.793L5.354 8.146a.5.5 0 1 0-.708.708l3 3z"/>
            </svg>
            Download Relacionamentos
        </a>
    </div>
    """
    return html.replace("</body>", js_snippet + "</body>")

@app.route('/clear_graph', methods=['POST'])
def clear_graph():
    """Route to clear the graph and reset history."""
    global visualization_history, current_viz_index, explored_nodes

    # Reset all variables related to the graph's history and exploration state
    visualization_history = []
    current_viz_index = 0
    explored_nodes = set()

    # Clear any active visualizations in the frontend by returning an empty HTML
    return jsonify({"status": "success", "message": "Graph cleared."})


@app.route('/descriptive-analysis', methods=['GET'])
def descriptive_analysis():
    page = 1  # Initial page
    per_page = 10
    offset = (page - 1) * per_page

    conn = sqlite3.connect('data_to_download.db')
    cursor = conn.cursor()

    # Fetch the first 10 PEPs for Auxílio Emergencial
    cursor.execute("""
        SELECT NOME, CPF, SIGLA_FUNCAO, UF, DT_INICIO_EXERCICIO, DT_FIM_EXERCICIO,
               QTD_MESES_RECEBIDOS, PRIMEIRO_MES_RECEBIMENTO, ULTIMO_MES_RECEBIMENTO
        FROM peps_aux_emer_full
        LIMIT ? OFFSET ?
    """, (per_page, offset))
    peps_aux = cursor.fetchall()

    # Fetch the first 10 PEPs for Bolsa Família
    cursor.execute("""
        SELECT NOME, CPF, SIGLA_FUNCAO, UF, DT_INICIO_EXERCICIO, DT_FIM_EXERCICIO,
               QTD_MESES_RECEBIDOS, PRIMEIRO_MES_RECEBIMENTO, ULTIMO_MES_RECEBIMENTO
        FROM peps_bolsa_fam_full
        LIMIT ? OFFSET ?
    """, (per_page, offset))
    peps_bf = cursor.fetchall()

    # Get the total counts for both tables to calculate pagination
    cursor.execute("SELECT COUNT(*) FROM peps_aux_emer_full")
    total_peps_aux = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM peps_bolsa_fam_full")
    total_peps_bf = cursor.fetchone()[0]

    has_next_aux = total_peps_aux > page * per_page
    has_next_bf = total_peps_bf > page * per_page

    conn.close()

    # Render both the Auxílio Emergencial and Bolsa Família tables in the same page
    return render_template('descriptive_analysis.html', peps_aux=peps_aux, 
                           peps_bf=peps_bf, 
                           page=page, 
                           has_next_aux=has_next_aux
                           , 
                           has_next_bf=has_next_bf
                           )


# Rota para paginação de Auxílio Emergencial
@app.route('/paginate-data-aux', methods=['GET'])
def paginate_data_aux():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    conn = sqlite3.connect('data_to_download.db')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT NOME, CPF, SIGLA_FUNCAO, UF, DT_INICIO_EXERCICIO, DT_FIM_EXERCICIO,
               QTD_MESES_RECEBIDOS, PRIMEIRO_MES_RECEBIMENTO, ULTIMO_MES_RECEBIMENTO
        FROM peps_aux_emer_full
        LIMIT ? OFFSET ?
    """, (per_page, offset))
    peps = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) FROM peps_aux_emer_full")
    total_peps = cursor.fetchone()[0]

    has_next_aux = total_peps > page * per_page
    conn.close()

    table_html = render_template('partials/pep_aux_emer_table_body.html', peps_aux=peps)
    pagination_html = render_template('partials/pagination_aux.html', page=page, has_next_aux=has_next_aux)

    return jsonify({'table': table_html, 'pagination': pagination_html})

@app.route('/paginate-data-bf', methods=['GET'])
def paginate_data_bf():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    conn = sqlite3.connect('data_to_download.db')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT NOME, CPF, SIGLA_FUNCAO, UF, DT_INICIO_EXERCICIO, DT_FIM_EXERCICIO,
               QTD_MESES_RECEBIDOS, PRIMEIRO_MES_RECEBIMENTO, ULTIMO_MES_RECEBIMENTO
        FROM peps_bolsa_fam_full
        LIMIT ? OFFSET ?
    """, (per_page, offset))
    peps_bf = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) FROM peps_bolsa_fam_full")
    total_peps_bf = cursor.fetchone()[0]

    has_next_bf = total_peps_bf > page * per_page
    conn.close()

    table_html = render_template('partials/pep_bf_table_body.html', peps_bf=peps_bf)
    pagination_html = render_template('partials/pagination_bf.html', page=page, has_next_bf=has_next_bf)

    return jsonify({'table': table_html, 'pagination': pagination_html})


@app.route('/download_peps_aux_emer')
def download_peps_aux_emer():
    conn = sqlite3.connect('data_to_download.db')
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT *
        FROM peps_aux_emer_full
    """)
    
    peps = cursor.fetchall()
    cursor.close()

    # Create the CSV file in memory
    output = []
    output.append(['NOME', 'CPF', 'SIGLA_FUNCAO', 'UF', 'DT_INICIO_EXERCICIO', 'DT_FIM_EXERCICIO', 'QTD_MESES_RECEBIDOS', 'PRIMEIRO_MES_RECEBIMENTO', 'ULTIMO_MES_RECEBIMENTO'])
    for pep in peps:
        output.append([pep[0], pep[1], pep[2], pep[3], pep[4], pep[5], pep[6], pep[7], pep[8]])
    
    si = io.StringIO(newline='')  # Ensures proper line endings
    si.write('\ufeff')  # Add BOM for UTF-8 encoding
    cw = csv.writer(si, delimiter=';')  # Use semicolon as the delimiter
    cw.writerows(output)
    
    response = make_response(si.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=peps_auxilio_emergencial.csv'
    response.headers['Content-type'] = 'text/csv; charset=utf-8'
    
    return response

@app.route('/download_peps_bf')
def download_peps_bf():
    conn_6 = sqlite3.connect('data_to_download.db')
    cursor = conn_6.cursor()
    
    cursor.execute("""
        SELECT *
        FROM peps_bolsa_fam_full
    """)
    
    peps = cursor.fetchall()
    cursor.close()

    # Create the CSV file in memory
    output = []
    output.append(['NOME', 'CPF', 'SIGLA_FUNCAO', 'UF', 'DT_INICIO_EXERCICIO', 'DT_FIM_EXERCICIO', 'QTD_MESES_RECEBIDOS', 'PRIMEIRO_MES_RECEBIMENTO', 'ULTIMO_MES_RECEBIMENTO'])
    for pep in peps:
        output.append([pep[0], pep[1], pep[2], pep[3], pep[4], pep[5], pep[6], pep[7], pep[8]])
    
    si = io.StringIO(newline='')  # Ensures proper line endings
    si.write('\ufeff')  # Add BOM for UTF-8 encoding
    cw = csv.writer(si, delimiter=';')  # Use semicolon as the delimiter
    cw.writerows(output)
    
    response = make_response(si.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=peps_bolsa_familia.csv'
    response.headers['Content-type'] = 'text/csv; charset=utf-8'
    
    return response

def removerAcentosECaracteresEspeciais(palavra):

    # Unicode normalize transforma um caracter em seu equivalente em latin.
    nfkd = unicodedata.normalize('NFKD', palavra)
    palavraSemAcento = u"".join([c for c in nfkd if not unicodedata.combining(c)])

    # Usa expressão regular para retornar a palavra apenas com números, letras e espaço
    # return re.sub('[^a-zA-Z0-9 \\\]', '', palavraSemAcento).upper()
    return re.sub(r'[^a-zA-Z0-9 \\]', '', palavraSemAcento).upper()



def find_connection_depth(graph, start_node, end_node, avoid_nodes=None, max_depth=10):
    """
    Verifica se dois nós estão conectados e retorna a profundidade da conexão, considerando a lista de nós a serem evitados.
    
    Parâmetros:
    - graph: O grafo NetworkX
    - start_node: O primeiro nó
    - end_node: O segundo nó
    - avoid_nodes: Lista de nós a serem evitados durante a exploração
    - max_depth: A profundidade máxima para a busca
    
    Retorna:
    - A profundidade da conexão se os nós estão conectados, -1 caso contrário
    """
    if avoid_nodes is None:
        avoid_nodes = set()

    visited = set()
    queue = [(start_node, 0)]

    while queue:
        current_node, current_depth = queue.pop(0)
        visited.add(current_node)

        if current_depth < max_depth:
            neighbors = set(graph.neighbors(current_node)) - visited
            neighbors = list(neighbors - set(avoid_nodes))
            queue.extend((neighbor, current_depth + 1) for neighbor in neighbors)

            if end_node in neighbors:
                return  f"As entidades {start_node} e {end_node} estão conectados na largura (BFS) de nível {current_depth + 1}.\n"      

    return f"As entidades {start_node} e {end_node} NÃO estão conectados."

def find_shortest_path(graph, start_node, target_node, avoid_nodes=None):
    if avoid_nodes is None:
        avoid_nodes = set()

    try:
        if nx.has_path(graph, start_node, target_node):
            shortest_path = nx.shortest_path(graph, source=start_node, target=target_node)
            return shortest_path
        else:
            return None
    except nx.NodeNotFound:
        return None
 
@app.route('/shortest_path', methods=['GET', 'POST'])
def shortest_path():
    result_caminho = None
    graph_data = None
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'caminho':
            with open('graph_mecai_8.pkl', 'rb') as file:
                G = pickle.load(file)
            
            # First entity data
            name1 = request.form['start_node_name1']
            node_type1 = request.form['node_type1']
            cpf1 = request.form.get('cpf1', '')
            cpf_type1 = request.form.get('cpf_type1')
            cnpj1 = request.form.get('cnpj1', '')
            cnpj_type1 = request.form.get('cnpj_type1')

            # Second entity data
            name2 = request.form['start_node_name2']
            node_type2 = request.form['node_type2']
            cpf2 = request.form.get('cpf2', '')
            cpf_type2 = request.form.get('cpf_type2')
            cnpj2 = request.form.get('cnpj2', '')
            cnpj_type2 = request.form.get('cnpj_type2')

            # Process first entity
            doc1 = cpf1 if node_type1 == 'PF' else cnpj1
            is_complete1 = (cpf_type1 == 'complete') if node_type1 == 'PF' else (cnpj_type1 == 'complete')
            node1_doc = doc1[3:9] if is_complete1 else doc1
            start_node1 = f"{node_type1}_{node1_doc}_{removerAcentosECaracteresEspeciais(name1)}"

            # Process second entity
            doc2 = cpf2 if node_type2 == 'PF' else cnpj2
            is_complete2 = (cpf_type2 == 'complete') if node_type2 == 'PF' else (cnpj_type2 == 'complete')
            node2_doc = doc2[3:9] if is_complete2 else doc2
            start_node2 = f"{node_type2}_{node2_doc}_{removerAcentosECaracteresEspeciais(name2)}"

            avoid_nodes = ['PEP', 'AUX_EMER', 'BOLSA_FAM']

            # Ensure the nodes exist in the graph
            if start_node1 not in G or start_node2 not in G:
                result_caminho = f"Não há conexão entre as entidades: {start_node1} e {start_node2} !"
            else:
                try:
                    # Try to find the shortest path
                    shortest_path_nodes = nx.shortest_path(G, source=start_node1, target=start_node2)
                    depth = find_connection_depth(G, start_node1, start_node2, max_depth=50)
                    result_caminho = depth
                    
                    # Create a subgraph with the nodes in the shortest path
                    subgraph = G.subgraph(shortest_path_nodes)
                    
                    # Prepare the data to be passed to the frontend
                    nodes = []
                    for node in subgraph.nodes():
                        # Assign node image based on the node type
                        if node.startswith("PF"):
                            image_path = "static/images/user.png"
                        elif node.startswith("PJ"):
                            image_path = "static/images/enterprise.png"
                        elif node.startswith("PEP"):
                            image_path = "static/images/PEP.png"
                        elif node.startswith("BOL") or node.startswith("AUX"):
                            image_path = "static/images/money_red.png"
                        else:
                            image_path = "static/images/money.png"

                        # Convert image to base64 and embed it
                        img_base64 = encode_image_to_base64(image_path)
                        nodes.append({
                            'id': node, 
                            'label': node, 
                            'image': f"data:image/png;base64,{img_base64}",
                            'shape': 'image',
                            'size': 30
                        })

                    # Fetch edges with 'tipo' attribute
                    edges = []
                    for u, v in subgraph.edges():
                        edge_type = subgraph.edges[u, v].get('tipo', 'undefined')
                        edges.append({
                            'from': u,
                            'to': v,
                            'label': edge_type,
                            'title': edge_type
                        })
                    
                    graph_data = {'nodes': nodes, 'edges': edges}
                    
                except nx.NetworkXNoPath:
                    result_caminho = "Não existe um caminho entre as duas entidades."
                except nx.NodeNotFound as e:
                    result_caminho = f"Erro: {str(e)}"
    
    return render_template('shortest_path.html', 
                         result_caminho=result_caminho, 
                         graph_data=graph_data,
                         submitted=request.method == 'POST')

@app.route('/peps_distribution')
def peps_distribution():
    return render_template('peps_distribution.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/contacts')
def contacts():
    return render_template('contacts.html')

if __name__ == '__main__':
    app.run()