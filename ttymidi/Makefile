CC ?= gcc
CFLAGS ?= -Wall -O2
LDFLAGS ?=
LDLIBS = -lasound -pthread

PREFIX ?= /usr
BINDIR = $(PREFIX)/bin

all: ttymidi

ttymidi: ttymidi-sysex.c
	$(CC) $(CFLAGS) $(CPPFLAGS) -o $@ $< $(LDFLAGS) $(LDLIBS)

install: ttymidi
	install -d $(DESTDIR)$(BINDIR)
	install -m 0755 ttymidi $(DESTDIR)$(BINDIR)/ttymidi

clean:
	rm -f ttymidi

.PHONY: all install clean
