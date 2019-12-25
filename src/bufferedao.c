/*  bufferedao.c: Copyright 2005 Joerg Lehmann 
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

/* written using the pyao wrapper by Andrew Chatham <andrew.chatham@duke.edu> */

#include <Python.h>
#include <stdlib.h>
#include <unistd.h>
#include <pthread.h>
#include <ao/ao.h>
#include <errno.h>
#include <assert.h>

#define NRITEMS() ((self->in >= self->out) ? self->in-self->out : self->in+self->buffersize-self->out)

//struct module_state {
//    PyObject *error;  
//    PyObject *log_debug; /* currently not used */
//    PyObject *log_error;
//};

// #define GETSTATE(m) ((struct module_state*)PyModule_GetState(m))

// global state

PyObject *error;  
PyObject *log_debug; /* currently not used */
PyObject *log_error;


static PyObject *bufferedaoerror;

typedef struct {
    char* buff;
    int bytes;
} bufitem;

// bufferedao extension type //

typedef struct {
    PyObject_HEAD

    /* properties of the ao device */
    int driver_id;
    ao_sample_format format;
    ao_option *options;

    ao_device *dev;              /* pointer to the ao_device if open, NULL otherwise */

    int ispaused;
    int done;

    /* ring buffer */
    int SIZE;                     /* size in bytes of one item in the buffer */
    int buffersize;               /* number of items in the buffer */
    bufitem *buffer;
    int in;                       /* position of next item put in the buffer */
    int out;                      /* position of next item read from buffer */
    pthread_mutex_t buffermutex;  /* mutex protecting the ring buffer */
    pthread_cond_t notempty;      /* condition variable signalizing that the ring buffer is not empty */
    pthread_cond_t notfull;       /* ... and not full */
    pthread_mutex_t restartmutex; /* mutex protecting the restart condition variable */
    pthread_cond_t restart;       /* condition variable signalizing that we should restart after being paused */
    pthread_mutex_t devmutex;     /* mutex protecting dev */
} bufferedao;


/* helper methods */

static ao_option *
py_options_to_ao_options(PyObject *py_options)
{
    Py_ssize_t pos = 0;
    PyObject *key, *val;
    ao_option *head = NULL;
    int ret;

    if ( !PyDict_Check(py_options) ) {
        PyErr_SetString(PyExc_TypeError, "options has to be a dictionary");
        return NULL;
    }

    while ( PyDict_Next(py_options, &pos, &key, &val) ) {
        if (!PyUnicode_Check(key) || !PyUnicode_Check(val)) {
            PyErr_SetString(PyExc_TypeError, "keys in options may only be strings");
            ao_free_options(head);
            return NULL;
        }
    }

    ret = ao_append_option(&head, PyUnicode_AsUTF8(key), PyUnicode_AsUTF8(val));
    if ( ret == 0 ) {
        PyErr_SetString(bufferedaoerror, "Error appending options");
        ao_free_options(head);
        return NULL;
    }

    return head;
}

/* type methods for bufferedao type */

static void
bufferedao_dealloc(bufferedao* self)
{
    ao_close(self->dev);
    ao_free_options(self->options);
    if (self->buffer) {
        int i;
        for (i=0; i<self->buffersize; i++)
            free(self->buffer[i].buff);
        free(self->buffer);
    }
    pthread_mutex_destroy(&self->buffermutex);
    pthread_cond_destroy(&self->notempty);
    pthread_cond_destroy(&self->notfull);
    pthread_mutex_destroy(&self->restartmutex);
    pthread_cond_destroy(&self->restart);
    pthread_mutex_destroy(&self->devmutex);
    Py_TYPE(self)->tp_free((PyObject*) self);
}

static PyObject *
bufferedao_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    bufferedao *self;
    int bufsize;
    char *driver_name;
    int i;
    PyObject *py_options = NULL;

    static char *kwlist[] = {"bufsize", "SIZE", "driver_name", "bits", "rate", "channels", "byte_format",
                                   "options", NULL};

    self = (bufferedao *)type->tp_alloc(type, 0);
    if ( !self )
        return NULL;

    /* default values for sample format */
    self->format.bits = 16;
    self->format.rate = 44100;
    self->format.channels = 2;
    self->format.byte_format = 4;    /* platform byte order */

    /* parse parameters... */
    if ( !PyArg_ParseTupleAndKeywords(args, kwds, "iis|iiiiO!", kwlist,
                                      &bufsize,
                                      &self->SIZE,
                                      &driver_name,
                                      &self->format.bits,
                                      &self->format.rate,
                                      &self->format.channels,
                                      &self->format.byte_format,
                                      &PyDict_Type, &py_options) ) {
        Py_DECREF(self);
        return NULL;
    }

    if ( (self->driver_id = ao_driver_id(driver_name)) == -1 ) {
        PyErr_SetString(bufferedaoerror, "unknown driver_name");
        Py_DECREF(self);
        return NULL;
    }

    /* ... and possibly contained options */
    self->options = NULL;
    if (py_options && PyDict_Size(py_options) ) {
        /* In the case of an empty dictionary, py_options_to_ao_options would return NULL.
         * Thus, we should (and need) not call it in this case */

        if ( !(self->options = py_options_to_ao_options(py_options)) ) {
            Py_DECREF(self);
            return NULL;
        }
    }

    /* calculate number of items in the ring buffer from bufsize which is in kB and SIZE in bytes */
    self->buffersize = 1024*bufsize/self->SIZE + 1;
    if ( !( self->buffer = (bufitem *) malloc(sizeof(bufitem) * self->buffersize) ) ) {
        Py_DECREF(self);
        PyErr_NoMemory();
        return NULL;
    }
    for (i=0; i<self->buffersize; i++) {
        if ( !( self->buffer[i].buff = (char *) malloc(sizeof(char) * self->SIZE) ) ) {
            /* deallocate everything already allocated if we run out of memory */
            int j;
            for (j=0; j<i; j++)
                free(self->buffer[j].buff);
            free(self->buffer);
            Py_DECREF(self);
            PyErr_NoMemory();
            return NULL;
        }
    }
    self->in = 0;
    self->out = 0;

    pthread_mutex_init(&self->buffermutex, 0);
    pthread_cond_init(&self->notempty, 0);
    pthread_cond_init(&self->notfull, 0);

    self->ispaused = 0;
    self->done = 0;
    pthread_mutex_init(&self->restartmutex, 0);
    pthread_cond_init(&self->restart, 0);
    pthread_mutex_init(&self->devmutex, 0);

    return (PyObject *)self;
}

/* own methods */

static PyObject *
bufferedao_start(bufferedao *self)
{
    char *buff;
    int bytes;
    int errorlogged;

    Py_BEGIN_ALLOW_THREADS
    while ( !self->done ) {
        pthread_mutex_lock(&self->restartmutex);
        while (self->ispaused)
           pthread_cond_wait(&self->restart, &self->restartmutex);
        pthread_mutex_unlock(&self->restartmutex);

        /* ring-buffer get code */
        pthread_mutex_lock(&self->buffermutex);
        while ( self->in == self->out )
           pthread_cond_wait(&self->notempty, &self->buffermutex);
        /* we can safely drop the mutex here, assuming that we are the only reader, and thus 
         * the only one modyfing self->in and the corresponding buffer item */
        pthread_mutex_unlock(&self->buffermutex);

        buff = self->buffer[self->out].buff;
        bytes = self->buffer[self->out].bytes;

        if (bytes) {
            pthread_mutex_lock(&self->devmutex);
            /* try to open audiodevice, if this has not yet happened.
             * This corresponds to the opendevice method in Python code. However, we have to be more careful here
             * since we have to guarantee, that the pointer we get has not been modified (i.e. set to NULL) by 
             * the closedevice method */
            errorlogged = 0;
            while (self->dev == NULL )  {
                self->dev = ao_open_live(self->driver_id, &self->format, self->options);
                if ( self->dev == NULL ) {
                    int errsv = errno;
                    char *ao_errorstring="";
                    char errorstring[128];
                    pthread_mutex_unlock(&self->devmutex);
                    if (!errorlogged) {
                        Py_BLOCK_THREADS
                        /* XXX report details of error */
                        switch (errsv) {
                        case AO_ENODRIVER: ao_errorstring = "No driver corresponds to driver_id."; break;
                        case AO_ENOTLIVE: ao_errorstring = "This driver is not a live output device."; break;
                        case AO_EBADOPTION: ao_errorstring = "A valid option key has an invalid value."; break;
                        case AO_EOPENDEVICE: ao_errorstring ="Cannot open the device."; break;
                        case AO_EFAIL: ao_errorstring = "Unknown failure"; break;
                        }
                        snprintf(errorstring, 128, "cannot open audio device: %s", ao_errorstring);
                        PyObject *result = PyObject_CallFunction(log_error, "s", errorstring);
                        Py_XDECREF(result);
                        Py_UNBLOCK_THREADS
                        errorlogged = 1;
                    }
                    sleep(1);
                    pthread_mutex_lock(&self->devmutex);
                }
            }
            ao_play(self->dev, buff, bytes);
            pthread_mutex_unlock(&self->devmutex);
        }

        /* we have to reacquire the mutex before sending the signal */
        pthread_mutex_lock(&self->buffermutex);
        self->out = (self->out + 1) % self->buffersize;
        pthread_mutex_unlock(&self->buffermutex);

        pthread_cond_signal(&self->notfull);
    }
    Py_END_ALLOW_THREADS

    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject *
bufferedao_play(bufferedao *self, PyObject *args)
{
    char *buff;
    int bytes;
    int len;
    if ( !PyArg_ParseTuple(args, "s#i", &buff, &len, &bytes) )
          return NULL;

    if ( len>self->SIZE ) {
        PyErr_SetString(bufferedaoerror, "buff too long");
        return NULL;
    }

    Py_BEGIN_ALLOW_THREADS
    /* ring-buffer put code */
    pthread_mutex_lock(&self->buffermutex);
    /* note that we can store actually only one item less then buffersize, because
     * otherwise we are not able to detect whether the ring buffer is empty or full */
    while ( NRITEMS() == self->buffersize-1 )
       pthread_cond_wait(&self->notfull, &self->buffermutex);
    /* we can safely drop the mutex here, assuming that we are the only writer, and thus 
     * the only one modyfing self->in and the corresponding buffer item */
    pthread_mutex_unlock(&self->buffermutex);

    memcpy(self->buffer[self->in].buff, buff, len);
    self->buffer[self->in].bytes = bytes;

    /* we have to reacquire the mutex before sending the signal */
    pthread_mutex_lock(&self->buffermutex);
    self->in = (self->in + 1) % self->buffersize;
    pthread_mutex_unlock(&self->buffermutex);

    pthread_cond_signal(&self->notempty);
    Py_END_ALLOW_THREADS

    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject *
bufferedao_closedevice(bufferedao *self)
{
    Py_BEGIN_ALLOW_THREADS
    pthread_mutex_lock(&self->devmutex);
    if (self->dev) {
        ao_close(self->dev);
        /* we use self->dev == NULL as a marker for a closed audio device */
        self->dev = NULL;
    }
    pthread_mutex_unlock(&self->devmutex);
    Py_END_ALLOW_THREADS

    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject *
bufferedao_queuelen(bufferedao *self)
{
    return PyFloat_FromDouble(1.0/(self->format.channels * self->format.bits / 8)
                              * self->SIZE / self->format.rate * NRITEMS());
}


static PyObject *
bufferedao_flush(bufferedao *self)
{
    Py_BEGIN_ALLOW_THREADS
    pthread_mutex_lock(&self->buffermutex);
    self->in = 0;
    self->out = 0;
    pthread_cond_signal(&self->notfull);
    pthread_mutex_unlock(&self->buffermutex);
    Py_END_ALLOW_THREADS

    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject *
bufferedao_pause(bufferedao *self)
{
    PyObject *retval;
    self->ispaused = 1;

    if ( !(retval = PyObject_CallMethod((PyObject *) self, "closedevice", NULL)) ) {
        return NULL;
    }
    Py_DECREF(retval);

    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject *
bufferedao_unpause(bufferedao *self)
{
    if ( self->ispaused ) {
        Py_BEGIN_ALLOW_THREADS
        pthread_mutex_lock(&self->restartmutex);
        self->ispaused = 0;
        pthread_mutex_unlock(&self->restartmutex);
        pthread_cond_signal(&self->restart);
        Py_END_ALLOW_THREADS
    }
    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject *
bufferedao_quit(bufferedao *self)
{
    PyObject *retval;
    self->done = 1;

    if ( !(retval = PyObject_CallMethod((PyObject *) self, "flush", NULL)) ) {
        return NULL;
    }
    Py_DECREF(retval);

    if ( !(retval = PyObject_CallMethod((PyObject *) self, "closedevice", NULL)) ) {
        return NULL;
    }
    Py_DECREF(retval);

    pthread_mutex_lock(&self->restartmutex);
    self->ispaused = 0;
    pthread_mutex_unlock(&self->restartmutex);
    pthread_cond_signal(&self->restart);

    Py_INCREF(Py_None);
    return Py_None;
}

/*
static int bufferedao_traverse(PyObject *m, visitproc visit, void *arg) {
    Py_VISIT(GETSTATE(m)->error);
    return 0;
}

static int bufferedao_clear(PyObject *m) {
    Py_CLEAR(GETSTATE(m)->error);
    return 0;
}
*/

static PyMethodDef bufferedao_methods[] = {
    {"start", (PyCFunction) bufferedao_start, METH_VARARGS,
     "start main processing routine (blocks and thus has to be called from a new thread)"
    },
    {"play", (PyCFunction) bufferedao_play, METH_VARARGS,
     "put buff, bytes on buffer"
    },
    {"closedevice", (PyCFunction) bufferedao_closedevice, METH_NOARGS,
     "Close audio device until it is needed again"
    },
    {"queuelen", (PyCFunction) bufferedao_queuelen, METH_NOARGS,
     "Return approximate length of currently buffered PCM data in seconds"
    },
    {"flush", (PyCFunction) bufferedao_flush, METH_NOARGS,
     "flush currently buffered PCM data"
    },
    {"pause", (PyCFunction) bufferedao_pause, METH_NOARGS,
     "Pause output"
    },
    {"unpause", (PyCFunction) bufferedao_unpause, METH_NOARGS,
     "Pause output"
    },
    {"quit", (PyCFunction) bufferedao_quit, METH_NOARGS,
     "Stop buffered output thread"
    },
    {NULL, NULL}  /* Sentinel */
};



// // the module only contains the bufferedao type, no methods
// static PyMethodDef module_methods[] = {
//     {NULL}  /* Sentinel */
// };

static PyTypeObject bufferedaoType = {
//    PyObject_HEAD_INIT(NULL)
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "bufferedao.bufferedao",
    .tp_doc = "bufferedao objects",
    .tp_basicsize = sizeof(bufferedao),
    .tp_itemsize = 0,
    .tp_dealloc = (destructor)bufferedao_dealloc,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_methods = bufferedao_methods,
    .tp_new = bufferedao_new,
};

static struct PyModuleDef bufferedao_module = {
        PyModuleDef_HEAD_INIT,
        .m_name ="bufferedao",
        .m_doc = "bufferedao module",
        .m_size = -1,       // sizeof(struct module_state),
        .m_methods = NULL,  // bufferedao_methods: None
        .m_slots = NULL,
        .m_traverse = NULL, // bufferedao_traverse,
        .m_clear = NULL,    // buferedao_clear,
        .m_free = NULL,     // bufferedao_free,
};


PyMODINIT_FUNC
PyInit_bufferedao(void) {

    PyObject *module = PyModule_Create(&bufferedao_module);

    printf("1\n");

    if (module == NULL)
        return NULL;

    PyObject* log_module;

    printf("2\n");
    /* import log module and fetch debug and error functions into module_state */
    if ( !(log_module = PyImport_ImportModule("log")) )
      return NULL;

    if ( !(log_debug = PyObject_GetAttrString(log_module, "debug")) ) {
      Py_DECREF(module);
      Py_DECREF(log_module);
      return NULL;
    }
    if ( !(log_error = PyObject_GetAttrString(log_module, "error")) ) {
      Py_DECREF(module);
      Py_DECREF(log_module);
      return NULL;
    }
    Py_DECREF(log_module);

    PyObject *result = PyObject_CallFunction(log_error, "s", "test_error");
    Py_XDECREF(result);
    result = PyObject_CallFunction(log_error, "s", "test_debug");
    Py_XDECREF(result);

    printf("3a\n");

    // create exception and add it to module
    error = PyErr_NewException("bufferedao.error", NULL, NULL);
    printf("3b\n");

    result = PyObject_CallFunction(log_error, "s", "test_debug2");
    Py_XDECREF(result);
    if (error == NULL) {
      Py_DECREF(module);
      Py_DECREF(log_debug);
      Py_DECREF(log_error);
      return NULL;
    }
    printf("3c\n");

    Py_INCREF(error);
    if (PyModule_AddObject(module, "error", error)<0) {
      Py_DECREF(module);
      Py_DECREF(error);
      return NULL;
    }
    printf("4\n");

    /* initialize the ao library */
    ao_initialize();
    printf("5\n");

    /* finalize and add extension type to module */
    if (PyType_Ready(&bufferedaoType) < 0) {
        Py_DECREF(module);
        Py_DECREF(log_debug);
        Py_DECREF(log_error);
        return NULL;
    }
    printf("6\n");

    Py_INCREF(&bufferedaoType);
    PyModule_AddObject(module, "bufferedao", (PyObject *)&bufferedaoType);

    printf("7\n");

    return module;
}
