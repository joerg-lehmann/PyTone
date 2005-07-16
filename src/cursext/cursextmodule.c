/*  cursextmodule.c: Copyright 2004 Johannes Mockenhaupt
 *
 *  This program is free software; you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation; either version 2 of the License, or
 *  (at your option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with this program; if not, write to the Free Software
 *  Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307,
 *  USA.
 */

#include <Python.h>
#include <curses.h>

/* the function this module is about ;-) */
static PyObject *useDefaultColors(PyObject *self, PyObject *args) {
       if (use_default_colors() == OK)
               return Py_BuildValue("i",1);
       else
               return Py_BuildValue("i",0);
}

/* table of functions this module provides */
static PyMethodDef CursExtMethods [] = {
       {"useDefaultColors", useDefaultColors, METH_NOARGS,
        "use terminal's default colors, enabling transparency." },
       {NULL, NULL, 0, NULL}
};

/* module initialisation */
/* PyMODINT_FUNC */
void initcursext(void) {
       Py_InitModule("cursext", CursExtMethods);
}

