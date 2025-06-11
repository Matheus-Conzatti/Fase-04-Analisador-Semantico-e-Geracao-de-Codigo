"""
    Trabalho de Compiladores - Analisador Léxico e Sintático para RPN
    Grupo: Grupo 6 - Calculadora RPN
    Integrantes:
    1. André Ruan Cesar Dal Negro
    2. Felipe Abdullah
    3. Matheus Conzatti de Souza
"""
import sys
import struct
import math
import os

# --- Classes para os Nós da Árvore de Sintaxe Abstrata (AST) ---
class ASTNode:
    """Nó base para a Árvore de Sintaxe Abstrata."""
    def __init__(self, value=None):
        self.value = value
        self.children = []

    def add_child(self, node):
        """Adiciona um nó filho."""
        self.children.append(node)

    def __repr__(self):
        """Representação de string para depuração."""
        return f"{self.__class__.__name__}({self.value if self.value is not None else ''})"

class ProgramNode(ASTNode):
    """Representa o programa completo (uma sequência de declarações/expressões)."""
    def __init__(self):
        super().__init__("PROGRAM")

class NumberNode(ASTNode):
    """Representa um número literal."""
    pass

class BinOpNode(ASTNode):
    """Representa uma operação binária (+, -, *, |, /, %, ^)."""
    def __init__(self, operator, left, right):
        super().__init__(operator)
        self.add_child(left)
        self.add_child(right)
        self.operator = operator
        self.left = left
        self.right = right

class MemAccessNode(ASTNode):
    """Representa o comando (MEM) - acesso ao valor da memória."""
    def __init__(self):
        super().__init__("MEM_ACCESS")

class MemStoreNode(ASTNode):
    """Representa o comando (V MEM) - armazenamento de valor na memória."""
    def __init__(self, value_node):
        super().__init__("MEM_STORE")
        self.add_child(value_node)
        self.value_node = value_node

class ResAccessNode(ASTNode):
    """Representa o comando (N RES) - acesso a resultados anteriores."""
    def __init__(self, index_node):
        super().__init__("RES_ACCESS")
        self.add_child(index_node)
        self.index_node = index_node
        
class IfNode(ASTNode):
    """Representa uma declaração if-then-else."""
    def __init__(self, condition, then_branch, else_branch=None):
        super().__init__("IF")
        self.add_child(condition)
        self.add_child(then_branch)
        if else_branch:
            self.add_child(else_branch)
        self.condition = condition
        self.then_branch = then_branch
        self.else_branch = else_branch

class ForNode(ASTNode):
    """Representa uma declaração de laço for."""
    def __init__(self, var_id_node, start_val_node, end_val_node, step_val_node, body_node):
        super().__init__("FOR")
        self.add_child(var_id_node)
        self.add_child(start_val_node)
        self.add_child(end_val_node)
        if step_val_node:
            self.add_child(step_val_node)
        self.add_child(body_node)
        self.var_id_node = var_id_node # Nó que representa o identificador da variável de loop
        self.start_val_node = start_val_node
        self.end_val_node = end_val_node
        self.step_val_node = step_val_node
        self.body_node = body_node # O corpo do loop (uma Expressao RPN)

class RPNCalculator:
    """
        Implementa uma calculadora para RPN com analisador léxico, sintático (LL(1) + AST)
        e avaliador para RPN, incluindo comandos especiais e estruturas de controle.
    """
    def __init__(self):
        """Inicializa a calculadora."""
        self.results = []
        self.memory = 0.0
        self.current_file = ""
        self.current_line_num = 0
        self.current_line_content = ""
        self.tokens = []        # Lista de tokens da expressão atual
        self.token_index = 0    # Índice do token atual no processo de parsing
        self.ast = None         # A AST gerada para a expressão atual

    # --- Funções de Conversão (Mantidas para referência, mas não usadas na avaliação) ---
    def convertFloatToHalf(self, f):
        """Converte float para half-precision (16 bits) IEEE 754."""
        # Implementação original mantida... (verificar correção se for usar)
        try:
            f32 = struct.unpack('>I', struct.pack('>f', f))[0]
            sign = (f32 >> 31) & 0x1
            exponent = ((f32 >> 23) & 0xFF) - 127
            mantissa = f32 & 0x007FFFFF
            if math.isnan(f): return 0x7E00 # Specific NaN
            if math.isinf(f): return 0x7C00 | (sign << 15)
            if exponent > 15: return 0x7C00 | (sign << 15) # Infinity
            if exponent < -14: return sign << 15  # Zero or Subnormal (simplified to 0)
            exponent_half = exponent + 15
            mantissa_half = mantissa >> 13
            return (sign << 15) | (exponent_half << 10) | mantissa_half
        except OverflowError:
             return 0x7C00 # Infinity for very large numbers

    def convertHalfToFloat(self, f16):
        """
            Converte half-precision (16 bits) para float IEEE 754.
        """
        # Implementação original mantida... (verificar correção se for usar)
        sign = (f16 >> 15) & 0x1
        exponent = (f16 >> 10) & 0x1F
        mantissa = f16 & 0x03FF
        if exponent == 0:
            if mantissa == 0: return 0.0 if not sign else -0.0
            f = mantissa / 1024.0
            return math.ldexp(f, -14) * (-1 if sign else 1)
        elif exponent == 0x1F:
            if mantissa == 0: return float('inf') if not sign else float('-inf')
            return float('nan')
        exponent -= 15
        mantissa += 1024
        f32 = (sign << 31) | ((exponent + 127) << 23) | (mantissa << 13)
        return struct.unpack('>f', struct.pack('>I', f32))[0]

    # --- Análise Léxica (Tokenizador Manual) ---
    def _custom_tokenize(self, expression):
        """
            Tokeniza a expressão manualmente, sem usar regex.
            Retorna uma lista de strings.
        """
        tokens = []
        i = 0
        n = len(expression)
        
        while i < n:
            char = expression[i]
            if char.isspace():
                i += 1
                continue
            
            # Operadores e Parênteses
            if char in ['+', '-', '*', '|', '/', '%', '^', '(', ')']:
                tokens.append(char)
                i += 1
                continue

            # Números (inteiros e flutuantes, incluindo negativos)
            # Prioriza o '-' como parte de um número negativo se seguido por um dígito
            if char.isdigit() or (char == '-' and i + 1 < n and expression[i+1].isdigit()):
                start = i
                if char == '-':
                    i += 1 # Consome o '-'
                
                while i < n and expression[i].isdigit():
                    i += 1
                
                if i < n and expression[i] == '.':
                    i += 1 # Consome o '.'
                    while i < n and expression[i].isdigit():
                        i += 1
                tokens.append(expression[start:i])
                continue
            
            # Palavras-chave (MEM, RES, SE, ENTAO, SENAO, PARA, DE, ATE, PASSO, etc.)
            if char.isalpha():
                start = i
                while i < n and (expression[i].isalpha() or expression[i].isdigit()): # Palavras podem conter números se forem IDs complexos
                    i += 1
                tokens.append(expression[start:i].upper()) # Guarda em maiúsculas para fácil comparação
                continue
            
            # Caractere inválido
            raise ValueError(f"Caractere inesperado encontrado: '{char}' na posição {i}")
        return tokens

    # --- Operações Matemáticas (Permanece o mesmo) ---
    def operate(self, a, b, operator):
        """Realiza a operação matemática (CORRIGIDA)."""
        if operator == '+': return a + b
        elif operator == '-': return a - b
        elif operator == '*': return a * b
        elif operator == '|': # Divisão Real
            if b == 0: raise ZeroDivisionError("Divisão real por zero.")
            return a / b
        elif operator == '/': # Divisão Inteira
            if b == 0: raise ZeroDivisionError("Divisão inteira por zero.")
            if not (a == int(a) and b == int(b)):
                raise TypeError("Operands for '/' must be integers.")
            return int(a) // int(b)
        elif operator == '%': # Resto Inteiro
            if b == 0: raise ZeroDivisionError("Módulo por zero.")
            if not (a == int(a) and b == int(b)):
                raise TypeError("Operands for '%' must be integers.")
            return int(a) % int(b)
        elif operator == '^': # Potenciação
            if not (b == int(b) and b >= 0):
                raise TypeError("Exponent must be a non-negative integer.")
            return math.pow(a, int(b))
        else:
            raise ValueError(f"Operador inválido '{operator}'")

    # --- Métodos Auxiliares para o Parser LL(1) ---
    def _get_current_token(self):
        """
            Retorna o token atual sem avançar.
        """
        if self.token_index < len(self.tokens):
            return self.tokens[self.token_index]
        return 'EOF' # Marca o fim da entrada

    def _advance_token(self):
        """
            Avança para o próximo token.
        """
        self.token_index += 1

    def _expect(self, expected_token_value):
        """
            Verifica se o token atual é o esperado e avança.
        """
        current_token = self._get_current_token()
        if current_token == expected_token_value:
            self._advance_token()
            return current_token
        else:
            raise SyntaxError(f"Erro de sintaxe na linha {self.current_line_num}: "
                              f"Esperado '{expected_token_value}', encontrado '{current_token}' "
                              f"na expressão: '{self.current_line_content}'")

    # --- Analisador Sintático LL(1) (Descida Recursiva) e Construtor da AST ---
    def parse_line_to_ast(self):
        """
            Ponto de entrada do parser para uma única linha (declaração/expressão).
            Assume que cada linha do arquivo é uma 'Declaracao' ou 'Expressao' de nível superior.
        """
        # Decide qual regra gramatical seguir com base no lookahead
        current_token = self._get_current_token()
        
        # Lookahead para determinar se é um comando especial, uma expressão RPN, IF ou FOR
        if current_token == '(':
            next_token = self.tokens[self.token_index + 1] if self.token_index + 1 < len(self.tokens) else None
            
            if next_token == 'SE': # if-then-else [cite: 29]
                return self._parse_if_declaration()
            elif next_token == 'PARA': # for loop [cite: 29]
                return self._parse_for_declaration()
            else: # Pode ser RPN comum ou (N RES), (V MEM), (MEM)
                return self._parse_expression()
        elif current_token == 'EOF': # Linha vazia ou fim do arquivo
            return None
        else: # Pode ser um número literal sozinho, se sua gramática permitir no nível superior
            return self._parse_expression() # _parse_expression já lida com NumberNode

    def _parse_expression(self):
        """
            Regra gramatical para Expressao:
            Expressao ::= '(' Termo Termo OP_ARITMETICA ')'
                        | ComandoEspecial
                        | NUMERO
        """
        current_token = self._get_current_token()
        if current_token == '(':
            self._expect('(')
            # Verifica o próximo token para determinar o tipo de expressão
            first_inner_token = self.tokens[self.token_index] if self.token_index < len(self.tokens) else None
            second_inner_token = self.tokens[self.token_index + 1] if self.token_index + 1 < len(self.tokens) else None

            # Check for (MEM)
            if first_inner_token == 'MEM':
                self._expect('MEM')
                self._expect(')')
                return MemAccessNode()
            
            # Check for (RES)
            try:
                # Tenta consumir um número para V ou N
                # NÃO AVANÇA TOKEN AINDA, apenas tenta converter para verificar tipo
                _ = float(first_inner_token)
                is_num_first_token = True
            except ValueError:
                is_num_first_token = False

            if is_num_first_token and (second_inner_token == 'MEM' or second_inner_token == 'RES'):
                num_node = self._parse_number() # Consome e cria NumberNode para V ou N
                keyword = self._get_current_token() # Pega MEM ou RES
                self._advance_token() # Consome MEM ou RES
                self._expect(')')

                if keyword == 'MEM':
                    return MemStoreNode(num_node)
                elif keyword == 'RES':
                    return ResAccessNode(num_node)
            else:
                # É uma operação RPN binária: (Termo Termo OP_ARITMETICA)
                left_term_node = self._parse_term()
                right_term_node = self._parse_term()
                operator = self._get_current_token()
                
                # Verifica se é um operador válido [cite: 13, 14, 15]
                if operator not in ['+', '-', '*', '|', '/', '%', '^']:
                     raise SyntaxError(f"Erro de sintaxe: Esperado operador aritmético, encontrado '{operator}'")
                self._advance_token() # Consome operador
                self._expect(')')
                return BinOpNode(operator, left_term_node, right_term_node)
        
        # Expressao ::= NUMERO
        elif current_token.isdigit() or (current_token == '-' and self.tokens[self.token_index + 1].isdigit()):
            return self._parse_number()
        else:
            raise SyntaxError(f"Erro de sintaxe na linha {self.current_line_num}: "
                              f"Esperado '(', ou NUMERO, encontrado '{current_token}' "
                              f"na expressão: '{self.current_line_content}'")

    # --- Análise Sintática para Termos ---
    def _parse_term(self):
        """
            Regra gramatical para Termo:
            Termo ::= Expressao | NUMERO
        """
        current_token = self._get_current_token()
        if current_token == '(':
            return self._parse_expression()
        elif current_token.isdigit() or (current_token == '-' and self.tokens[self.token_index + 1].isdigit()):
            return self._parse_number()
        else:
            raise SyntaxError(f"Erro de sintaxe na linha {self.current_line_num}: "
                              f"Esperado '(', ou NUMERO, encontrado '{current_token}' "
                              f"na expressão: '{self.current_line_content}'")

    # --- Análise Sintática para Números ---
    def _parse_number(self):
        """Cria um nó de número a partir do token atual."""
        token_value = self._get_current_token()
        try:
            value = float(token_value) # Números podem ser reais
            node = NumberNode(value)
            self._advance_token()
            return node
        except ValueError:
            raise SyntaxError(f"Erro de sintaxe na linha {self.current_line_num}: "
                              f"Esperado um número literal, encontrado '{token_value}' "
                              f"na expressão: '{self.current_line_content}'")

    # --- Análise Sintática para Declarações If e For ---
    def _parse_if_declaration(self):
        """
            Regra gramatical para IfDeclaracao:
            IfDeclaracao ::= '(' 'SE' Expressao 'ENTAO' Expressao ('SENAO' Expressao)? ')'
        """
        self._expect('(')
        self._expect('SE')
        condition_node = self._parse_expression() # A condição é uma expressão RPN
        self._expect('ENTAO')
        then_branch_node = self._parse_expression() # O bloco 'then' é uma expressão RPN

        else_branch_node = None
        if self._get_current_token() == 'SENAO':
            self._expect('SENAO')
            else_branch_node = self._parse_expression() # O bloco 'else' é uma expressão RPN
        
        self._expect(')')
        return IfNode(condition_node, then_branch_node, else_branch_node)

    def _parse_for_declaration(self):
        """
            Regra gramatical para ForDeclaracao:
            ForDeclaracao ::= '(' 'PARA' ID 'DE' NUMERO 'ATE' NUMERO ('PASSO' NUMERO)? Expressao ')'
        """
        self._expect('(') # Verifica se o próximo token é '('
        self._expect('PARA') # Verifica se o próximo token é 'PARA'
        var_id_node = self._parse_number() # Adapte se 'ID' for um nome literal (string)
        self._expect('DE') # Verifica se o próximo token é 'DE'
        start_val_node = self._parse_number() # O valor inicial do laço é um número
        self._expect('ATE') # Verifica se o próximo token é 'ATE'
        end_val_node = self._parse_number() # O valor final do laço é um número
        step_val_node = None # O passo é opcional, então pode ser None
        # Verifica se o próximo token é 'PASSO' para o passo opcional
        if self._get_current_token() == 'PASSO':
            self._expect('PASSO')
            step_val_node = self._parse_number()
        
        body_node = self._parse_expression() # O corpo do laço é uma expressão RPN
        self._expect(')')
        return ForNode(var_id_node, start_val_node, end_val_node, step_val_node, body_node)

    # --- Avaliação da AST ---
    def evaluate_ast(self, node):
        """
            Percorre a AST e avalia as expressões.
        """
        if isinstance(node, NumberNode):
            return node.value
        elif isinstance(node, BinOpNode):
            left_val = self.evaluate_ast(node.left)
            right_val = self.evaluate_ast(node.right)
            return self.operate(left_val, right_val, node.operator)
        elif isinstance(node, MemAccessNode):
            return self.memory 
        elif isinstance(node, MemStoreNode):
            value = self.evaluate_ast(node.value_node)
            self.memory = value
            return value
        elif isinstance(node, ResAccessNode):
            index = int(self.evaluate_ast(node.index_node)) # N é um inteiro não negativo [cite: 26]
            if index < 0: raise ValueError("N para RES deve ser não-negativo.")
            if index >= len(self.results):
                raise IndexError(f"Não há {index+1} resultados anteriores para RES.")
            return self.results[-(index + 1)] # Acessa do final da lista de resultados
        elif isinstance(node, IfNode):
            condition_val = self.evaluate_ast(node.condition)
            if condition_val != 0: 
                return self.evaluate_ast(node.then_branch)
            elif node.else_branch:
                return self.evaluate_ast(node.else_branch)
            return None # If sem else e condição falsa não retorna valor ou implícito 0
        elif isinstance(node, ForNode):
            start = int(self.evaluate_ast(node.start_val_node))
            end = int(self.evaluate_ast(node.end_val_node))
            step = int(self.evaluate_ast(node.step_val_node)) if node.step_val_node else 1
            
            last_evaluated_result = None
            for i in range(start, end + 1, step):
                current_loop_result = self.evaluate_ast(node.body_node)
                last_evaluated_result = current_loop_result
            return last_evaluated_result
        elif isinstance(node, ProgramNode):
            # Um ProgramNode contém uma lista de declarações/expressões.
            # Avalia cada uma e armazena o resultado, retornando o último.
            last_result_of_program = None
            for child_node in node.children:
                pass # A avaliação real é feita por `evaluate_expression`
            return None # O resultado da avaliação da linha é retornado por `evaluate_expression`
        else:
            raise NotImplementedError(f"Avaliação não implementada para o tipo de nó: {type(node)}")

    # --- Impressão da AST (Representação Canônica) ---
    def print_ast(self, node, level=0, prefix="Root: "):
        """Imprime a Árvore de Sintaxe Abstrata de forma indentada."""
        indent = "  " * level
        if node is None:
            print(f"{indent}{prefix}None")
            return

        node_info = f"{node.__class__.__name__}"
        if node.value is not None:
            node_info += f" (Value: {node.value})"
        
        print(f"{indent}{prefix}{node_info}")

        for i, child in enumerate(node.children):
            child_prefix = f"Child {i}: "
            self.print_ast(child, level + 1, prefix=child_prefix)

    # --- Processamento da Expressão (Ponto de Entrada Principal) ---
    def evaluate_expression(self, expression_string):
        """
            Ponto de entrada para avaliação.
            1. Tokeniza a expressão.
            2. Constrói a AST usando o parser LL(1).
            3. Imprime a AST.
            4. Avalia a AST.
            5. Armazena o resultado.
        """
        self.current_line_content = expression_string.strip()
        self.tokens = [] # Reinicia tokens para a linha atual
        self.token_index = 0 # Reinicia índice para a linha atual

        if not self.current_line_content or self.current_line_content.startswith('#'):
            return None # Ignora linhas vazias ou comentários
        try:
            print(f"Expressão {self.current_line_num}: {self.current_line_content}")
            
            # 1. Análise Léxica (Tokenização)
            self.tokens = self._custom_tokenize(self.current_line_content)
            # Adiciona EOF para o parser sinalizar o fim da entrada da linha
            self.tokens.append('EOF') 
            print(f"Tokens: {self.tokens}")

            # 2. Análise Sintática (Construção da AST)
            # Para cada linha, chamamos o parser para construir a AST para aquela linha.
            # A gramática presume que cada linha é uma 'Declaracao' ou 'Expressao'.
            current_line_ast = self.parse_line_to_ast()

            print("\n--- Árvore Sintática Abstrata (AST) ---")
            self.print_ast(current_line_ast)
            print("----------------------------------------")

            # 3. Avaliação da AST
            result = self.evaluate_ast(current_line_ast)
            
            # Armazena o resultado para o comando (N RES)
            # O escopo é por arquivo, então os resultados são cumulativos dentro do arquivo. [cite: 28]
            self.results.append(result)
            return result

        except Exception as e:
            self.generate_error_report(str(e))
            return None

    # --- Relatório de Erro (Permanece o mesmo) ---
    def generate_error_report(self, error_msg):
        """
            Gera um relatório de erro.
        """
        print("\n=== Relatório de Erro ===")
        print(f"Arquivo: {self.current_file}")
        print(f"Linha: {self.current_line_num}")
        print(f"Código: {self.current_line_content}")
        print(f"Erro: {error_msg}")
        print("=======================\n")

    # --- Processamento de Arquivo (Permanece o mesmo, adaptado para nova avaliação) ---
    def process_input(self, path):
        """Processa arquivos ou diretórios."""
        if os.path.isfile(path):
            if path.endswith('.txt'):
                self.process_file(path)
            else:
                print(f"Erro: '{path}' não é um arquivo .txt")
        elif os.path.isdir(path):
            for fname in sorted(os.listdir(path)): # Ordena para processamento consistente
                if fname.endswith('.txt'):
                    self.process_file(os.path.join(path, fname))
        else:
            print(f"Erro: '{path}' não encontrado.")

    def process_file(self, filename):
        """
            Processa um arquivo linha por linha.
        """
        self.current_file = os.path.basename(filename)
        print(f"\n---- Processando Arquivo: {self.current_file} ----\n")
        
        # Limpa resultados e memória por arquivo, conforme "Cada arquivo de textos é um escopo de aplicação" [cite: 28]
        self.results = [] 
        self.memory = 0.0

        with open(filename, 'r') as f:
            lines = f.readlines()

        for i, line in enumerate(lines):
            self.current_line_num = i + 1
            # evaluate_expression agora contém toda a lógica de parsing e avaliação para a linha
            result = self.evaluate_expression(line)
            if result is not None:
                print(f"Resultado Final da Linha: {result}\n")
            else:
                # O erro já foi reportado por generate_error_report
                if line.strip() and not line.strip().startswith('#'): # Só imprime se não for linha vazia/comentário
                    print("Avaliação da linha falhou.\n")

    def _check_type(self, node):
        """
            Realiza a verificação de tipos para um nó da AST.
            Retorna o tipo do nó ('float' ou 'int').
        """
        if isinstance(node, NumberNode):
            # Verifica se é um número inteiro.
            if node.value.value == int(node.value):
                return 'int'
            return 'float'
        elif isinstance(node, BinOpNode):
            left_type = self._check_type(node.left)
            right_type = self._check_type(node.right)

            # Operações que requerem interos.
            if node.operator in ['/', '%', '^']:
               if left_type != 'int' or right_type != 'int':
                    raise TypeError(f"Operação {node.operator} requer operandos inteiros")
            return 'int'
            # Operações que podem ser float
            return 'float'
        elif isinstance(node, (MemAccessNode, MemStoreNode)):
            return 'float'

# --- Função Principal ---
def main():
    """
        Função principal.
    """
    calculator = RPNCalculator()

    if len(sys.argv) > 1:
        path = sys.argv[1]
        calculator.process_input(path)
    else:
        print("Uso: python3 seu_script.py <arquivo_ou_diretorio_entrada>")

if __name__ == "__main__":
    main()