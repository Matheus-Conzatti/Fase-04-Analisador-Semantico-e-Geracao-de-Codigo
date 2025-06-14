MCU = atmega328p
F_CPU = 16000000
CC = avr-gcc
OBJCOPY = avr-objcopy
CFLAGS = -mmcu=$(MCU) -DF_CPU=$(F_CPU)UL -Os -Wall

all: main.hex

main.elf: output.S
	$(CC) $(CFLAGS) -o $@ $<

main.hex: main.elf
	$(OBJCOPY) -O ihex -R .eeprom $< $@

flash: main.hex
	avrdude -p atmega328p -c stk500v1 -P COM3 -b 19200 -U flash:w:main.hex

clean:
	rm -f *.o *.elf *.hex