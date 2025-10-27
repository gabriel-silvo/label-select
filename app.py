import pandas as pd
import os
import io
import re
import unicodedata
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

# Funções de Normalização das Classes de NICE
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

def normalize_classes_to_string(val):
    """
    Função principal: Converte um campo de classe em uma string ordenada
    de classes normalizadas.
    Ex: "16, 35, 42" -> "16, 35, 42"
    Ex: "Ncl(12) 36" -> "36"
    Ex: "25/10, Ncl(11) 16" -> "16, 25"
    """
    if val is None or pd.isna(val):
        return ""

    s_val = str(val).strip()
    
    items = s_val.split(',') # Divide por vírgula para tratar múltiplos valores
    
    normalized_list = [normalize_single_class(v) for v in items] # Normaliza cada item individualmente
    
    # Limpa valores vazios e garante que são numéricos para ordenar
    cleaned_list = []
    for item in normalized_list:
        num_match = re.findall(r'\b\d+\b', item)
        if num_match:
            cleaned_list.append(int(num_match[0]))
    
    cleaned_list.sort()
    
    return ", ".join(map(str, cleaned_list))

# ROTA DE COMPARAÇÃO
@app.route('/compare', methods=['GET', 'POST'])
def compare():
    if request.method == 'POST':
        file_input1 = request.files.get('file_brandious') # Modelo: relatorio_colidencias...
        file_input2 = request.files.get('file_competitor') # Modelo: Lista Colidências Processo x Processo

        if not file_input1 or not file_input2:
            return render_template('compare.html', error="Erro: Por favor, envie os dois arquivos.")
        
        try:
            # Carregar planilhas
            df_input1 = pd.read_excel(file_input1)
            df_input2 = pd.read_excel(file_input2)

            # Extrair Número da RPI para Título ---
            rpi_prefix = "RPI_NA" # Valor padrão
            try:
                # Tenta pegar do Input 1
                if 'revista' in df_input1.columns:
                    first_rpi = df_input1['revista'].dropna().iloc[0]
                    rpi_prefix = f"RPI_{normalize_number(first_rpi)}"
                # Se não achar, tenta pegar do Input 2
                elif 'RPI' in df_input2.columns:
                    first_rpi = df_input2['RPI'].dropna().iloc[0]
                    rpi_prefix = f"RPI_{normalize_number(first_rpi)}"
            except Exception:
                pass # Mantém "RPI_NA" se falhar

            # Renomear colunas para um Padrão Interno Unificado
            map_input1 = {
                'marca_monitorada': 'marca_monit', 'processo_monitorado': 'proc_monit',
                'classe_marca_monitorada': 'classe_monit', 'marca_colidente': 'marca_colid',
                'processo_colidente': 'proc_colid', 'classe_marca_colidente': 'classe_colid',
            }
            df1 = df_input1.rename(columns={k: v for k, v in map_input1.items() if k in df_input1.columns})

            df_input2.columns = [str(c).strip() for c in df_input2.columns]
            if 'Processo Cadastrado' not in df_input2.columns:
                return render_template('compare.html', error="Erro: O Input 2 deve ser uma planilha 'Lista Colidências Processo x Processo'.")

            map_input2 = {
                'Marca do Processo Cadastrado': 'marca_monit', 'Processo Cadastrado': 'proc_monit',
                'Classe do Processo Cadastrado': 'classe_monit', 'Marca do Processo da RPI': 'marca_colid',
                'Processo da RPI': 'proc_colid', 'Classe do processso da RPI': 'classe_colid',
            }
            df2 = df_input2.rename(columns={k: v for k, v in map_input2.items() if k in df_input2.columns})

            # Normalização de Chave
            key_columns_orig = ['marca_monit', 'proc_monit', 'classe_monit', 'marca_colid', 'proc_colid', 'classe_colid']
            for col in key_columns_orig:
                if col not in df1.columns: df1[col] = None
                if col not in df2.columns: df2[col] = None
            key_columns_norm = ['marca_monit_norm', 'proc_monit_norm', 'classe_monit_norm', 'marca_colid_norm', 'proc_colid_norm', 'classe_colid_norm']
            df1['marca_monit_norm'] = df1['marca_monit'].apply(normalize_string)
            df1['proc_monit_norm'] = df1['proc_monit'].apply(normalize_number)
            df1['classe_monit_norm'] = df1['classe_monit'].apply(normalize_classes_to_string)
            df1['marca_colid_norm'] = df1['marca_colid'].apply(normalize_string)
            df1['proc_colid_norm'] = df1['proc_colid'].apply(normalize_number)
            df1['classe_colid_norm'] = df1['classe_colid'].apply(normalize_classes_to_string)
            df2['marca_monit_norm'] = df2['marca_monit'].apply(normalize_string)
            df2['proc_monit_norm'] = df2['proc_monit'].apply(normalize_number)
            df2['classe_monit_norm'] = df2['classe_monit'].apply(normalize_classes_to_string)
            df2['marca_colid_norm'] = df2['marca_colid'].apply(normalize_string)
            df2['proc_colid_norm'] = df2['proc_colid'].apply(normalize_number)
            df2['classe_colid_norm'] = df2['classe_colid'].apply(normalize_classes_to_string)
            df1['composite_key'] = df1[key_columns_norm].apply(lambda row: '|'.join(row), axis=1)
            df2['composite_key'] = df2[key_columns_norm].apply(lambda row: '|'.join(row), axis=1)

            # Realizar o "diff"
            set_keys1 = set(df1['composite_key'])
            set_keys2 = set(df2['composite_key'])
            keys_only_in_1 = set_keys1 - set_keys2
            keys_only_in_2 = set_keys2 - set_keys1
            df_diff1 = df1[df1['composite_key'].isin(keys_only_in_1)].copy()
            df_diff1['Fonte_da_Diferenca'] = 'Brandious'
            df_diff2 = df2[df2['composite_key'].isin(keys_only_in_2)].copy()
            df_diff2['Fonte_da_Diferenca'] = 'outro'
            df_final_diff = pd.concat([df_diff1, df_diff2], ignore_index=True, sort=False)

            # Agregação pelo par de marcas
            def join_unique(series):
                unique_values = series.dropna().astype(str).unique()
                unique_values = [v for v in unique_values if v.strip()]
                unique_values.sort()
                return ", ".join(unique_values)
            grouping_cols = ['marca_monit_norm', 'marca_colid_norm', 'Fonte_da_Diferenca']
            agg_cols = {
                'proc_monit_norm': join_unique,
                'classe_monit_norm': join_unique,
                'proc_colid_norm': join_unique,
                'classe_colid_norm': join_unique
            }
            for col in grouping_cols:
                if col not in df_final_diff.columns: df_final_diff[col] = None
            for col in agg_cols:
                if col not in df_final_diff.columns: df_final_diff[col] = None
            df_grouped = df_final_diff.groupby(grouping_cols, as_index=False).agg(agg_cols)

            # Renomear colunas para o formato de Saída
            output_map_final = {
                'marca_monit_norm': 'Marca Monitorada',
                'proc_monit_norm': 'Processo Monitorado',
                'classe_monit_norm': 'Classe Marca Monitorada',
                'marca_colid_norm': 'Marca Colidente',
                'proc_colid_norm': 'Processo Colidente',
                'classe_colid_norm': 'Classe Marca Colidente',
                'Fonte_da_Diferenca': 'Fonte da Diferenca'
            }
            df_final_output = df_grouped.rename(columns=output_map_final)
            
            # Etapa de Ordenação (Brandious primeiro)
            def strip_accents(s):
                s = str(s)
                return unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode('utf-8').upper()
            df_final_output['sort_key_monit'] = df_final_output['Marca Monitorada'].apply(strip_accents)
            df_final_output['sort_key_colid'] = df_final_output['Marca Colidente'].apply(strip_accents)
            df_final_output.sort_values(
                by=['Fonte da Diferenca', 'sort_key_monit', 'sort_key_colid'],
                ascending=[True, True, True],
                inplace=True
            )
            df_final_output.drop(columns=['sort_key_monit', 'sort_key_colid'], inplace=True)
            
            # índice para criar o ID
            df_final_output.reset_index(drop=True, inplace=True)
            df_final_output.insert(0, 'ID', df_final_output.index + 1)

            output_columns_order = [
                'ID',
                'Marca Monitorada', 'Processo Monitorado', 'Classe Marca Monitorada',
                'Marca Colidente', 'Processo Colidente', 'Classe Marca Colidente',
                'Fonte da Diferenca'
            ]
            for col in output_columns_order:
                if col not in df_final_output.columns:
                    df_final_output[col] = None
            df_final_output = df_final_output[output_columns_order]

            # 9. Gerar Arquivo e Tabela de Preview
            timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
            download_filename = f"{rpi_prefix} - Relatório Brandious x Processos concorrentes {timestamp}.xlsx"
            download_path = os.path.join(app.config['UPLOAD_FOLDER'], download_filename)

            with pd.ExcelWriter(download_path, engine='openpyxl') as writer:
                df_final_output.to_excel(writer, index=False, sheet_name='Diferencas')
                worksheet = writer.sheets['Diferencas']
                worksheet.autofilter = worksheet.dimensions

            table_html = df_final_output.to_html(classes='results-table', index=False, max_rows=20, na_rep='')

            return render_template('compare.html', 
                                   table_html=table_html,
                                   download_url=url_for('static', filename=f'uploads/{download_filename}'),
                                   download_filename=download_filename)

        except Exception as e:
            return render_template('compare.html', error=f"Erro ao processar os arquivos: {e}")

    return render_template('compare.html')

@app.route('/validate-lists', methods=['GET', 'POST'])
def validate_lists():
    if request.method == 'POST':
        file1 = request.files.get('file_brandious')
        file2 = request.files.get('file_competitor')

        if not file1 or not file2:
            return render_template('validate.html', error="Erro: Por favor, envie os dois arquivos.")
        
        try:
            df1 = pd.read_excel(file1)
            df2 = pd.read_excel(file2)
            
            df1.columns = [str(c).strip() for c in df1.columns]
            df2.columns = [str(c).strip() for c in df2.columns]

            if 'Marca Original' in df1.columns:
                df_mxm = df1
                df_pxp = df2
            elif 'Marca Original' in df2.columns:
                df_mxm = df2
                df_pxp = df1
            else:
                return render_template('validate.html', error="Erro: Não foi possível identificar a planilha 'Marca x Marca'.")

            if 'Processo Cadastrado' not in df_pxp.columns:
                 return render_template('validate.html', error="Erro: Não foi possível identificar a planilha 'Processo x Processo'.")

            # Mapeamento de colunas para a chave (Par de Marcas)
            mxm_map = {'Marca Original': 'marca_monit', 'Marca Colidência': 'marca_colid'}
            pxp_map = {'Marca do Processo Cadastrado': 'marca_monit', 'Marca do Processo da RPI': 'marca_colid'}
            
            df_mxm_renamed = df_mxm.rename(columns=mxm_map)
            df_pxp_renamed = df_pxp.rename(columns=pxp_map)
            
            # Cria a chave composta (Par de Marcas)
            df_mxm_renamed['key'] = df_mxm_renamed['marca_monit'].apply(normalize_string) + '|' + df_mxm_renamed['marca_colid'].apply(normalize_string)
            df_pxp_renamed['key'] = df_pxp_renamed['marca_monit'].apply(normalize_string) + '|' + df_pxp_renamed['marca_colid'].apply(normalize_string)

            # Cria os sets e faz o diff
            set_mxm = set(df_mxm_renamed['key'])
            set_pxp = set(df_pxp_renamed['key'])

            only_in_mxm = set_mxm - set_pxp
            only_in_pxp = set_pxp - set_mxm
            
            diffs = []
            for key in only_in_mxm:
                parts = key.split('|')
                diffs.append({'Marca Monitorada': parts[0], 'Marca Colidente': parts[1], 'Fonte': 'Apenas em Marca x Marca'})
            
            for key in only_in_pxp:
                parts = key.split('|')
                diffs.append({'Marca Monitorada': parts[0], 'Marca Colidente': parts[1], 'Fonte': 'Apenas em Processo x Processo'})

            if not diffs:
                # SUCESSO! Nenhuma diferença
                return render_template('validate.html', success_message="Nenhuma diferença encontrada. As listas de pares de marcas são consistentes.")

            # Se houver diferenças, formata-as para a tabela
            df_diffs = pd.DataFrame(diffs)
            df_diffs.sort_values(by=['Fonte', 'Marca Monitorada', 'Marca Colidente'], inplace=True)
            
            table_html = df_diffs.to_html(classes='results-table', index=False, max_rows=100, na_rep='')

            return render_template('validate.html', 
                                   table_html=table_html)

        except Exception as e:
            return render_template('validate.html', error=f"Erro ao processar os arquivos: {e}")

    return render_template('validate.html')

if __name__ == '__main__':
    app.run(debug=True)