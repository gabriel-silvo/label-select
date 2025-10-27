import pandas as pd
import os
import io
import re
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)
# Configura uma pasta para salvar os relatórios gerados
# Usamos os.path.join para funcionar em qualquer sistema operacional
UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Garante que a pasta de uploads exista
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        user_text = request.form['text_input']
        return redirect(url_for('label', text=user_text))
    return render_template('index.html')

@app.route('/label')
def label():
    user_text = request.args.get('text', '')
    return render_template('label.html', text=user_text)

# FUNÇÕES DE NORMALIZAÇÃO
def normalize_string(val):
    """Converte para string, maiúsculo e remove espaços."""
    if val is None or pd.isna(val):
        return ""
    return str(val).strip().upper()

def normalize_number(val):
    """Converte para string, remove '.0' de números lidos como float."""
    if val is None or pd.isna(val):
        return ""
    return str(val).strip().split('.')[0]

def normalize_single_class(val):
    """
    Helper: Normaliza UMA ÚNICA string de classe para o seu número base.
    Ex: "Ncl(12) 36" -> "36"
    Ex: "25/10" -> "25"
    Ex: " 42 " -> "42"
    """
    s_val = str(val).strip()
    
    # Regra: "25/10" -> "25"
    if '/' in s_val:
        match = re.search(r'^\b(\d+)\b', s_val)
        return match.group(1) if match else s_val
    
    # Regra: "Ncl(12) 36" -> "36"
    if 'Ncl' in s_val or 'ncl' in s_val:
        nums = re.findall(r'\b\d+\b', s_val)
        return nums[-1] if nums else s_val
        
    # Regra: Apenas "42" ou "  42  "
    nums = re.findall(r'\b\d+\b', s_val)
    return nums[0] if nums else s_val

def normalize_classes_to_list(val):
    """
    Função principal: Converte um campo de classe em uma LISTA de classes normalizadas.
    Ex: "16, 35, 42" -> ["16", "35", "42"]
    Ex: "Ncl(12) 36" -> ["36"]
    Ex: "25/10" -> ["25"]
    """
    if val is None or pd.isna(val):
        return [""]

    s_val = str(val).strip()
    
    # Regra: "16, 35, 42"
    if ',' in s_val:
        return [normalize_single_class(v) for v in s_val.split(',')]

    # Se não for vírgula, é um caso único (ex: "Ncl(12) 36" ou "25/10")
    # Retorna uma lista com o único item normalizado
    return [normalize_single_class(s_val)]

# ROTA DE COMPARAÇÃO
@app.route('/compare', methods=['GET', 'POST'])
def compare():
    if request.method == 'POST':
        file_input1 = request.files.get('file_brandious') # Modelo: relatorio_colidencias...
        file_input2 = request.files.get('file_competitor') # Modelo: Lista Colidências...

        if not file_input1 or not file_input2:
            return render_template('compare.html', error="Erro: Por favor, envie os dois arquivos.")
        
        try:
            # Carregar planilhas
            df_input1 = pd.read_excel(file_input1)
            df_input2 = pd.read_excel(file_input2)

            # Renomear colunas do Input 1
            map_input1 = {
                'revista': 'rpi', 'marca_monitorada': 'marca_monit',
                'processo_monitorado': 'proc_monit', 'classe_marca_monitorada': 'classe_monit',
                'marca_colidente': 'marca_colid', 'processo_colidente': 'proc_colid',
                'classe_marca_colidente': 'classe_colid', 'similaridade': 'similaridade',
                'despacho': 'despacho', 'titular_monitorado': 'titular_monit',
                'titular_colidente': 'titular_colid',
            }
            df1 = df_input1.rename(columns={k: v for k, v in map_input1.items() if k in df_input1.columns})

            # Padronização da Similaridade (Input 1) - Apenas garante que é um número, sem multiplicar
            if 'similaridade' in df1.columns:
                df1['similaridade'] = pd.to_numeric(df1['similaridade'], errors='coerce')
                df1['similaridade'] = df1['similaridade'].round(0).where(pd.notna, None)

            # Detectar e Renomear colunas do Input 2
            df_input2.columns = [str(c).strip() for c in df_input2.columns]
            if 'Marca Original' in df_input2.columns: # Marca x Marca
                map_input2 = {
                    'RPI': 'rpi', 'Marca Original': 'marca_monit',
                    'NCL(s) Marca Original': 'classe_monit', 'Marca Colidência': 'marca_colid',
                    'NCL(s) Marca Colidência': 'classe_colid', 'Nível': 'similaridade',
                    'Titular': 'titular_colid',
                }
            elif 'Processo Cadastrado' in df_input2.columns: # Processo x Processo
                map_input2 = {
                    'Marca do Processo Cadastrado': 'marca_monit', 'Processo Cadastrado': 'proc_monit',
                    'Classe do Processo Cadastrado': 'classe_monit', 'Marca do Processo da RPI': 'marca_colid',
                    'Processo da RPI': 'proc_colid', 'Classe do processso da RPI': 'classe_colid',
                    'Nível': 'similaridade', 'Titular do Processo da RPI': 'titular_colid',
                }
            else:
                return render_template('compare.html', error="Erro: Formato do Input 2 (Lista Colidências) não reconhecido.")
            
            df2 = df_input2.rename(columns={k: v for k, v in map_input2.items() if k in df_input2.columns})

            # Padronização da Similaridade (Input 2)
            if 'similaridade' in df2.columns:
                # Converte 'similaridade' (que veio de 'Nível') para numérico
                df2['similaridade'] = pd.to_numeric(df2['similaridade'], errors='coerce')
                df2['similaridade'] = (df2['similaridade'] * 100).round(0).where(pd.notna, None)
            
            # Normalização das Classes
            key_columns_orig = ['rpi', 'marca_monit', 'proc_monit', 'classe_monit', 'marca_colid', 'proc_colid', 'classe_colid']
            for col in key_columns_orig:
                if col not in df1.columns: df1[col] = None
                if col not in df2.columns: df2[col] = None
            
            df1['classe_monit'] = df1['classe_monit'].apply(normalize_classes_to_list)
            df1['classe_colid'] = df1['classe_colid'].apply(normalize_classes_to_list)
            df2['classe_monit'] = df2['classe_monit'].apply(normalize_classes_to_list)
            df2['classe_colid'] = df2['classe_colid'].apply(normalize_classes_to_list)

            # EXPLODIR as linhas com múltiplas classes
            df1 = df1.explode('classe_monit', ignore_index=True)
            df1 = df1.explode('classe_colid', ignore_index=True)
            df2 = df2.explode('classe_monit', ignore_index=True)
            df2 = df2.explode('classe_colid', ignore_index=True)

            # Normalização de Chave
            key_columns_norm = [
                'rpi_norm', 'marca_monit_norm', 'proc_monit_norm', 'classe_monit_norm',
                'marca_colid_norm', 'proc_colid_norm', 'classe_colid_norm'
            ]
            
            df1['rpi_norm'] = df1['rpi'].apply(normalize_number)
            df1['marca_monit_norm'] = df1['marca_monit'].apply(normalize_string)
            df1['proc_monit_norm'] = df1['proc_monit'].apply(normalize_number)
            df1['classe_monit_norm'] = df1['classe_monit'].apply(normalize_string)
            df1['marca_colid_norm'] = df1['marca_colid'].apply(normalize_string)
            df1['proc_colid_norm'] = df1['proc_colid'].apply(normalize_number)
            df1['classe_colid_norm'] = df1['classe_colid'].apply(normalize_string)

            df2['rpi_norm'] = df2['rpi'].apply(normalize_number)
            df2['marca_monit_norm'] = df2['marca_monit'].apply(normalize_string)
            df2['proc_monit_norm'] = df2['proc_monit'].apply(normalize_number)
            df2['classe_monit_norm'] = df2['classe_monit'].apply(normalize_string)
            df2['marca_colid_norm'] = df2['marca_colid'].apply(normalize_string)
            df2['proc_colid_norm'] = df2['proc_colid'].apply(normalize_number)
            df2['classe_colid_norm'] = df2['classe_colid'].apply(normalize_string)
            
            df1['composite_key'] = df1[key_columns_norm].apply(lambda row: '|'.join(row), axis=1)
            df2['composite_key'] = df2[key_columns_norm].apply(lambda row: '|'.join(row), axis=1)

            # Realizar o "diff"
            set_keys1 = set(df1['composite_key'])
            set_keys2 = set(df2['composite_key'])
            keys_only_in_1 = set_keys1 - set_keys2
            keys_only_in_2 = set_keys2 - set_keys1

            df_diff1 = df1[df1['composite_key'].isin(keys_only_in_1)].copy()
            df_diff1['Fonte_da_Diferenca'] = 'Apenas no Input 1 (Relatório)'
            df_diff2 = df2[df2['composite_key'].isin(keys_only_in_2)].copy()
            df_diff2['Fonte_da_Diferenca'] = 'Apenas no Input 2 (Lista)'

            # Prepara o dataFrame final
            df_final_diff = pd.concat([df_diff1, df_diff2], ignore_index=True, sort=False)

            # Renomear colunas para o formato de Saída
            output_map = {
                'rpi': 'revista', 'marca_monit': 'marca_monitorada',
                'proc_monit': 'processo_monitorado', 'classe_monit': 'classe_marca_monitorada',
                'marca_colid': 'marca_colidente', 'proc_colid': 'processo_colidente',
                'classe_colid': 'classe_marca_colidente', 'similaridade': 'similaridade',
            }
            df_final_diff.rename(columns=output_map, inplace=True)
            
            output_columns_order = [
                'revista', 'marca_monitorada', 'processo_monitorado', 'classe_marca_monitorada',
                'marca_colidente', 'processo_colidente', 'classe_marca_colidente',
                'similaridade', 'Fonte_da_Diferenca'
            ]
            
            for col in output_columns_order:
                if col not in df_final_diff.columns:
                    df_final_diff[col] = None
            
            df_final_diff = df_final_diff[output_columns_order]

            # Gerar Arquivo e Tabela de Preview
            timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
            download_filename = f"relatorio_diferencas_{timestamp}.xlsx"
            download_path = os.path.join(app.config['UPLOAD_FOLDER'], download_filename)
            
            df_final_diff.to_excel(download_path, index=False)
            table_html = df_final_diff.to_html(classes='results-table', index=False, max_rows=20, na_rep='')

            return render_template('compare.html', 
                                   table_html=table_html,
                                   download_url=url_for('static', filename=f'uploads/{download_filename}'))

        except Exception as e:
            return render_template('compare.html', error=f"Erro ao processar os arquivos: {e}")

    # GET: exibe a página de upload
    return render_template('compare.html')

if __name__ == '__main__':
    app.run(debug=True)