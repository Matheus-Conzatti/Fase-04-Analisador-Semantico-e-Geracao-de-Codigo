import sys
import os
import struct
from collections import defaultdict

# Funções de conversão float-half float
def float_to_half(f):
    """Converte float (32 bits) para half-float (16 bits)"""
    bin = struct.unpack('>I', struct.pack('>f', f))[0]
    sign = (bin >> 16) & 0x8000
    exponent = ((bin >> 23) & 0xFF) - 127 + 15
    mantissa = (bin >> 13) & 0x03FF

    if exponent <= 0:
        return sign
    elif exponent >= 31:
        return sign | 0x7C00
    return sign | (exponent << 10) | mantissa

def half_to_float(f16):
    """Converte half-float (16 bits) para float (32 bits)"""
    sign = (f16 >> 15) & 0x0001
    exponent = (f16 >> 10) & 0x001F
    fraction = f16 & 0x03FF

    f32_sign = sign << 31
    if exponent == 0:
        if fraction == 0:
            return struct.unpack('>f', struct.pack('>I', f32_sign))[0]
        else:
            exponent = 1
            while (fraction & 0x0400) == 0:
                fraction <<= 1
                exponent -= 1
            fraction &= 0x03FF
            f32_exponent = (127 - 15 + exponent) << 23
            f32_fraction = fraction << 13
    elif exponent == 0x1F:
        f32_exponent = 0xFF << 23
        f32_fraction = fraction << 13
    else:
        f32_exponent = (127 - 15 + exponent) << 23
        f32_fraction = fraction << 13

    f32_bits = f32_sign | f32_exponent | f32_fraction
    return struct.unpack('>f', struct.pack('>I', f32_bits))[0]

class AnalizerSemantic:
    def __init__(self):
        self.tableSymbols = defaultdict(dict)
        self.stack_types = []
        self.scope_current = "global"
        self.counter_labels = 0

    def new_label(self):
        self.counter_labels += 1
        return f"label_{self.counter_labels}"
    
    def verify_type(self, operator, type1, type2):
        if operator in ['/', '%']:
            if type1 != 'int' or type2 != 'int':
                raise TypeError(f"Operador {operator} requer operandos inteiros")
            return 'int'
        elif operator == '|':
            return 'float'
        elif operator == '^':
            if type2 != 'int':
                raise TypeError("O expoente deve ser inteiro")
            return type1
        else:
            if 'float' in [type1, type2]:
                return 'float'
            return 'int'
        
    def determine_type(self, value):
        try:
            if '.' in value or 'e' in value.lower():
                float(value)
                return 'float'
            else:
                int(value)
                return 'int'
        except ValueError:
            raise TypeError(f"Valor inválido: {value}")

class GeneratorAssembly:
    def __init__(self):
        self.registrars = ['r16', 'r17', 'r18', 'r19', 'r20', 'r21', 'r22', 'r23']
        self.counter_labels = 0
        self.stack_assembly = []
        self.used_memory = 0
        self.float_size = 4
        self.use_half_float = False

    def set_half_float(self, use_half):
        self.use_half_float = use_half
        self.float_size = 2 if use_half else 4

    def new_label(self):
        self.counter_labels += 1
        return f"label_{self.counter_labels}"
    
    def prolog(self):
        code = [
            "; Código para ATmega328P",
            "#include <avr/io.h>",
            "",
            ".section .data",
            "MEMORY: .space {}".format(self.float_size),
            "RESULT: .space {}".format(10*self.float_size),
            "",
            ".section .text",
            ".global main",
            "",
            "main:",
            "    ldi r16, hi8(RAMEND)",
            "    out _SFR_IO_ADDR(SPH), r16",
            "    ldi r16, lo8(RAMEND)",
            "    out _SFR_IO_ADDR(SPL), r16"
        ]
        
        if self.use_half_float:
            code.append("    ; Operações half-float seriam implementadas aqui")
        else:
            code.append("    ; Operações float de 32-bits seriam implementadas aqui")
            
        return code
    
    def epilog(self):
        return ["loop:", "    rjmp loop"]
    
    def reload_value(self, value, type_val):
        if type_val == 'int':
            value_int = int(value)
            if value_int < 0:
                value_int = (1 << 16) + value_int  # Conversão para complemento de 2
            
            low = value_int & 0xFF
            high = (value_int >> 8) & 0xFF
            
            return [
                f"    ldi r16, {low}",
                f"    ldi r17, {high}"
            ]
        else:
            if self.use_half_float:
                half = float_to_half(float(value))
                return [
                    f"    ldi r16, lo8({half})",
                    f"    ldi r17, hi8({half})"
                ]
            else:
                bytes_float = struct.pack('>f', float(value))
                vals = struct.unpack('>BBBB', bytes_float)
                return [
                    f"    ldi r16, {vals[0]}",
                    f"    ldi r17, {vals[1]}",
                    f"    ldi r18, {vals[2]}",
                    f"    ldi r19, {vals[3]}"
                ]
    
    def operation_arithmetic(self, operator, type_val):
        if type_val == 'int':
            if operator == '+':
                return ["    add r16, r18", "    adc r17, r19"]
            elif operator == '-':
                return ["    sub r16, r18", "    sbc r17, r19"]
            elif operator == '*':
                return ["    call multiply_16bit"]
            elif operator == '/':
                return ["    call divide_16bit"]
            elif operator == '%':
                return ["    call modulo_16bit"]
        else:
            if self.use_half_float:
                return [f"    call half_float_{operator}"]
            else:
                return [f"    call float_{operator}"]

class CompilerRPN:
    def __init__(self):
        self.analizer = AnalizerSemantic()
        self.generator = GeneratorAssembly()
        self.results = []
        self.memory = 0.0
        self.use_half_float = False

    def set_half_float(self, use_half):
        self.use_half_float = use_half
        self.generator.set_half_float(use_half)

    def tokenizer_expression(self, expression):
        tokens = []
        current = ""
        in_paren = False
        
        expression = expression.strip()
        
        # Tratamento especial para comandos MEM e RES
        if expression == "(MEM)":
            return ['(', 'MEM', ')']
        elif expression.endswith(" MEM)"):
            parts = expression[:-1].split()  # Remove o ) final
            return ['(', parts[1], 'MEM', ')']
        elif expression.endswith(" RES)"):
            parts = expression[:-1].split()  # Remove o ) final
            return ['(', parts[1], 'RES', ')']
        
        # Processamento normal para outras expressões
        for char in expression:
            if char == ' ':
                if current:
                    tokens.append(current)
                    current = ""
            elif char == '(':
                tokens.append(char)
                in_paren = True
            elif char == ')':
                if current:
                    tokens.append(current)
                    current = ""
                tokens.append(char)
                in_paren = False
            else:
                current += char
        
        if current:
            tokens.append(current)
        
        return tokens

    def evaluate_expression(self, tokens):
        stack = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            
            if token == '(':
                j = i + 1
                count = 1
                while j < len(tokens) and count > 0:
                    if tokens[j] == '(': count += 1
                    elif tokens[j] == ')': count -= 1
                    j += 1
                
                if count != 0:
                    raise ValueError("Parênteses desbalanceados")
                
                subexpr = tokens[i+1:j-1]
                
                if len(subexpr) == 1 and subexpr[0] == 'MEM':
                    result = self.memory
                elif len(subexpr) == 2 and subexpr[1] == 'MEM':
                    self.memory = float(subexpr[0])
                    result = self.memory
                elif len(subexpr) == 2 and subexpr[1] == 'RES':
                    n = int(subexpr[0])
                    if n < len(self.results):
                        result = self.results[-(n+1)]
                    else:
                        raise ValueError(f"Nenhum resultado {n} passos para trá")
                else:
                    result = self.evaluate_expression(subexpr)
                
                if self.use_half_float and isinstance(result, float):
                    result = half_to_float(float_to_half(result))
                
                stack.append(result)
                i = j
            elif token == ')':
                i += 1
            elif token in ['+', '-', '*', '|', '/', '%', '^']:
                if len(stack) < 2:
                    raise ValueError(f"O operador {token} precisa de 2 operandos")
                b = stack.pop()
                a = stack.pop()
                stack.append(self.operate(a, b, token))
                i += 1
            else:
                try:
                    if '.' in token or 'e' in token.lower():
                        num = float(token)
                        if self.use_half_float:
                            num = half_to_float(float_to_half(num))
                        stack.append(num)
                    else:
                        stack.append(int(token))
                    i += 1
                except ValueError:
                    raise ValueError(f"Invalid token: {token}")
        
        if len(stack) != 1:
            raise ValueError("Invalid expression")
        
        return stack[0]

    def operate(self, a, b, operator):
        ops = {
            '+': lambda x,y: x+y,
            '-': lambda x,y: x-y,
            '*': lambda x,y: x*y,
            '|': lambda x,y: x/y if y!=0 else float('nan'),
            '/': lambda x,y: x//y if y!=0 else float('nan'),
            '%': lambda x,y: x%y if y!=0 else float('nan'),
            '^': lambda x,y: x**y if isinstance(y,int) and y>=0 else float('nan')
        }
        return ops[operator](a, b)

    def compile_file(self, input_file, output_file="output.S"):  # Note a mudança para .S
        try:
            with open(input_file, 'r') as f:
                lines = [line.strip() for line in f if line.strip()]

            asm_code = self.generator.prolog()

            for idx, line in enumerate(lines):
                try:
                    tokens = self.tokenizer_expression(line)
                    result = self.evaluate_expression(tokens)
                    self.results.append(result)
                    
                    type_val = 'float' if isinstance(result, float) else 'int'
                    
                    asm_code.append(f"; Line {idx+1}: {line} = {result}")
                    asm_code.extend(self.generator.reload_value(str(result), type_val))
                    
                    if self.use_half_float:
                        offset = idx * 2
                        asm_code.extend([
                            f"    sts RESULT+{offset}, r16",
                            f"    sts RESULT+{offset}+1, r17"
                        ])
                    else:
                        offset = idx * 4
                        asm_code.extend([
                            f"    sts RESULT+{offset}, r16",
                            f"    sts RESULT+{offset}+1, r17",
                            f"    sts RESULT+{offset}+2, r18",
                            f"    sts RESULT+{offset}+3, r19"
                        ])
                
                except Exception as e:
                    print(f"Error line {idx+1}: {str(e)}")
                    asm_code.append(f"; ERROR: {str(e)}")

            asm_code.extend(self.generator.epilog())

            with open(output_file, 'w') as f:
                f.write('\n'.join(asm_code))

            print(f"Sucesso na compilação. Saída: {output_file}")
            return True
        
        except Exception as e:
            print(f"Erro na compilação: {str(e)}")
            return False

def main():
    if len(sys.argv) < 2:
        print("Use: python compiler.py <input_file> [output_file] [--half-float]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else "output.S"  # .S em vez de .asm
    use_half_float = '--half-float' in sys.argv
    
    if not os.path.isfile(input_file):
        print(f"Error: Arquivo '{input_file}' não encontrado.")
        sys.exit(1)

    compiler = CompilerRPN()
    compiler.set_half_float(use_half_float)
    
    print(f"\nCompilando: {input_file}")
    if use_half_float:
        print("Usando half-float (16-bit) precision")
    else:
        print("Usando single-precision (32-bit) floats")
    print("----------------------------------")

    if compiler.compile_file(input_file, output_file):
        print("\nCompilação bem-sucedida!")
    else:
        print("\nCompilação concluída com erros")

if __name__ == "__main__":
    main()