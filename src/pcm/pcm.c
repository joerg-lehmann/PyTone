/*  pcm.c: Copyright 2002 Joerg Lehmann 
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

/* rate conversion:
 *  based on XMMS Crossfade Plugin
 *  Copyright (C) 2000-2001  Peter Eisenlohr <p.eisenlohr@gmx.net>
 *  based on the original OSS Output Plugin
 *  Copyright (C) 1998-2000  Peter Alm, Mikael Alm, Olle Hallnas, Thomas Nilsson 
 *  and 4Front Technologies
 *  Rate conversion for 16bit stereo samples.
 * 
 *  The algorithm (Least Common Multiple Linear Interpolation) was
 *  adapted from the rate conversion code used in
 *
 *    sox-12.16, Copyright 1998  Fabrice Bellard, originally
 *               Copyright 1991  Lance Norskog And Sundry Contributors.
 *  
 */

#include <Python.h>
#include <stdio.h>
#include <sys/types.h>
#include <assert.h>


/* Note: in all routines, we assume, that we deal with 16 bit stereo PCM data */

static void mix(char *b, const char *b1, 
		const char *b2, 
		int l,
		float *mixingratio,
		float mixingrate) {

  int16_t *ib  = (int16_t *) b;
  int16_t *ib1 = (int16_t *) b1;
  int16_t *ib2 = (int16_t *) b2;
  int il = l/2;

  float f = *mixingratio;
  float df = mixingrate/2;	/* we deal with stereo data */

  if (df>=0)
    while (il--) {
      *ib++ = *ib1++ * (1-f) + *ib2++ * f;
      f += df;
      if (f>1) f=1;
    }
  else
    while (il--) {
      *ib++ = *ib1++ * (1-f) + *ib2++ * f;
      f += df;
      if (f<0) f=0;
    }

  *mixingratio = f;
  
}

static PyObject *py_mix(PyObject *self, PyObject *args) {
  PyObject *returnObj = NULL;

  char *b1;
  int l1;

  char *b2;
  int l2;

  char *dummy=0;       /* buffer used, if l1!=l2 */

  PyObject *buffobj;
  char *b;             /* here goes the mixed stream */
  int l;
      
  float mixingratio;
  float mixingrate;

  if (PyArg_ParseTuple(args, 
		       "t#t#ff", 
		       &b1, &l1,
		       &b2, &l2,
		       &mixingratio,
		       &mixingrate)) {
      if (l1<l2) {
	  if (!(dummy = (char *) malloc(l2)))
	      return NULL;

          Py_BEGIN_ALLOW_THREADS

          memcpy((void *) dummy, (void *) b1, l1); 
          /* fill rest with zeros */
          memset((void *) (dummy+l1), 0, l2-l1); 

          Py_END_ALLOW_THREADS

          /* now proceed, as if nothing has ever happend...*/
          b1 = dummy;
          l1 = l2;
      }
      else if (l1>l2) {
	  if (!(dummy = (char *) malloc(l1)))
	      return NULL;

          Py_BEGIN_ALLOW_THREADS

          memcpy((void *) dummy, (void *) b2, l2); 
          /* fill rest with zeros */
          memset((void *) (dummy+l2), 0, l1-l2); 

          Py_END_ALLOW_THREADS

          /* now proceed, as if nothing has ever happend...*/
          b2 = dummy;
          l2 = l1;
      }

      l = l1;

      /* get new buffer object from python */
      buffobj = PyBuffer_New(l);

      /* use the internal python argument parser to get b*/
      PyArg_Parse(buffobj, "t#", &b, &l);

      /* now do the real work*/
      Py_BEGIN_ALLOW_THREADS
      mix(b, b1, b2, l, &mixingratio, mixingrate);
      Py_END_ALLOW_THREADS

      /* build up return structure */
      returnObj = Py_BuildValue("Of", buffobj, mixingratio);

      Py_DECREF(buffobj);  

      if (dummy)
	  free(dummy);
  }
  return returnObj;
		       
}

/* greatest common divisor */

static long long gcd(long m, long n) {
  long r;
  while(1) {
    r = m % n;
    if (r == 0) return n;
    m = n;
    n = r;
  }
}

/* least common multiplier */

static long long lcm(int i, int j)
{
  return ((long long ) i * j) / gcd(i, j);
}

static int rate_convert(char *in_c, int lin, char *out_c, int lout, 
			int in_rate, int out_rate,
			int firstsample, 
			int16_t *last_l, int16_t *last_r) {

  long long lcm_rate  = lcm(in_rate, out_rate);
  int in_skip   = lcm_rate / in_rate;
  int out_skip  = lcm_rate / out_rate;
  int samplenr   = lin/4; 		     /* number of samples */
  int16_t *in_i  = (int16_t* ) in_c;
  int16_t *out_i = (int16_t* ) out_c;
  int in_ofs     = 0;
  int out_ofs    = 0;
  int emitted    = 0;


  /* take last_l and last_r for first sample from input sample */
  if (firstsample) {
    *last_l = in_i[0];
    *last_r = in_i[1];
  }

  /* interpolation loop */
  for(;;) {

    /* advance input range to span next output ??? */
    while ( (in_ofs + in_skip) <= out_ofs ) {
      *last_l  = *in_i++;
      *last_r  = *in_i++;
      in_ofs += in_skip;
      
      samplenr--;

      if (samplenr == 0) 
	return emitted*4;
    }

    *out_i++ = *last_l + (((float) in_i[0] - *last_l)
			  * (out_ofs - in_ofs)
			  / in_skip);
    
    *out_i++ = *last_r + (((float) in_i[1] - *last_r)
			  * (out_ofs - in_ofs)
			  / in_skip);
    
    /* count emitted samples*/
    emitted++;

    assert(emitted*4<=lout);

    /* advance to next output */
    out_ofs += out_skip;
    
    /* long samples with high LCM's overrun counters! */
    if(out_ofs == in_ofs)
      out_ofs = in_ofs = 0;
  }
  
  /* we never arrive here */
  return 0;
}

static PyObject *py_rate_convert(PyObject *self, PyObject *args) {
  PyObject *returnObj = NULL;

  char *in_c;			/* input data */
  int lin;			/* length of in_c */
  int in_rate;			/* input sampling rate */

  char *out_c;			/* output data */
  int lout;			/* length of out_c */
  int out_rate;			/* output sampling rate */

  char *newout_c=0;             /* dummy buffer for output data */

  PyObject *py_pre_out_c; 	/* append output to this buffer */
  PyObject *py_start_pre_out;	/* and start from here */
  char *pre_out_c = NULL;
  int lpre_out = 0;
  int start_pre_out = 0;

  PyObject *py_last_l;
  PyObject *py_last_r;

  int16_t last_l;
  int16_t last_r;

  int firstsample;		/* are we dealing with the first sample */

  if (PyArg_ParseTuple(args, 
		       "t#iOOiOO", 
		       &in_c, &lin,
		       &in_rate,
		       &py_pre_out_c,
		       &py_start_pre_out,
		       &out_rate,
		       &py_last_l, 
		       &py_last_r
		       )) {
    
    PyObject *py_out;		/* python object for output buffer*/
    char *b;			/* temporary variable */
    int l;

    int emitted;		/* length of output stream <= out_c */

    if (py_last_l!=Py_None && py_last_r!=Py_None) {
      int i;
      firstsample = 0;
      PyArg_Parse(py_last_l, "i", &i); last_l = i;
      PyArg_Parse(py_last_r, "i", &i); last_r = i;
    } 
    else 
      firstsample = 1;

    /* get data of prefix, if present */
    if (py_pre_out_c!=Py_None && py_start_pre_out!=Py_None) {
      PyArg_Parse(py_pre_out_c, "t#", &pre_out_c, &lpre_out); 
      PyArg_Parse(py_start_pre_out, "i", &start_pre_out); 

      pre_out_c += start_pre_out;
      lpre_out -= start_pre_out;
    }

    if (in_rate!=out_rate) {

      /* allocate space for resampled output */
      lout = lin*out_rate/in_rate + 4;
      if (!(newout_c = (char *) malloc(lout)))
	return NULL;

      out_c = newout_c;

      /* now do the real work*/
      Py_BEGIN_ALLOW_THREADS
	emitted=  rate_convert(in_c, lin, out_c, lout,
			       in_rate, out_rate,
			       firstsample,
			       &last_l, &last_r);
      Py_END_ALLOW_THREADS
    }
    else {
      /* we only need to copy the input data */
      emitted = lin;
      out_c = in_c;
    }

    /* get new buffer object from python for prefixed data + resampled output */
    py_out = PyBuffer_New(lpre_out + emitted);

    /* use the internal python argument parser to get b*/
    PyArg_Parse(py_out, "t#", &b, &l);
      
    /* now we copy our result */
    Py_BEGIN_ALLOW_THREADS
    memcpy((void *) b, (void *) pre_out_c, lpre_out); 
    memcpy((void *) (b+lpre_out), (void *) out_c, emitted); 
      
    /* free space for dummy buffers if it has been allocated before */
    if (newout_c)
        free(newout_c);

    Py_END_ALLOW_THREADS
      
    /* build up return structure */
    returnObj = Py_BuildValue("Oii", py_out, (int) last_l, (int) last_r);

    Py_DECREF(py_out);  
  }
  return returnObj;
		       
}

/* interleave stereo channels from mono file */

static PyObject *py_upsample(PyObject *self, PyObject *args) {
  PyObject *returnObj = NULL;

  char *in_c;			/* input data */
  int lin;			/* length of in_c */
  char *out_c;			/* output data */

  PyObject *py_out;		/* python object for output buffer*/

  int16_t *in_i;
  int16_t *out_i;
  char *b;
  int l;
  int i, j;
    

  if (PyArg_ParseTuple(args, "t#", &in_c, &lin)) {
    Py_BEGIN_ALLOW_THREADS

    if (!(out_c = (char *) malloc(2*lin)))
      return NULL;

    in_i = (int16_t* ) in_c;
    out_i = (int16_t* ) out_c;
    
    for (i=0, j=0; i<lin; i+=2, j++) {
      out_i[i] = in_i[j];
      out_i[i+1] = in_i[j];
    }
    Py_END_ALLOW_THREADS

    /* get new buffer object from python for prefixed data + resampled output */
    py_out = PyBuffer_New(2*lin);

    /* use the internal python argument parser to get b*/
    PyArg_Parse(py_out, "t#", &b, &l);
    memcpy((void *) b, (void *) out_c, 2*lin);

    free(out_c);
    returnObj = py_out;
  }
  return returnObj;
}

/* scale(buff, factor):

inplace scale all elements of buf (interpreted as signed int16) by factor
*/

static PyObject *py_scale(PyObject *self, PyObject *args) {
  PyObject *returnObj = NULL;
  char *b_c;
  int16_t *b_i;  /* the same as pointer to 16 bit ints */
  int l;
  float factor;
  int i;

  if (PyArg_ParseTuple(args, "t#f", &b_c, &l, &factor )) {
      b_i  = (int16_t *) b_c;
      
      Py_BEGIN_ALLOW_THREADS
      for (i=0; i<l/2; i++) {
          double r = b_i[i] * factor;
          if (r>32768) b_i[i] = 32768;
          else if (r<-32767) b_i[i] = -32767;
          else b_i[i] = (int) r;
      }
      Py_END_ALLOW_THREADS
    Py_INCREF(Py_None);
    returnObj = Py_None;
  }
  return returnObj;
}

/* exported methods */

static PyMethodDef pcm_methods[] = {
  {"mix", py_mix,  METH_VARARGS},
  {"rate_convert", py_rate_convert,  METH_VARARGS},
  {"upsample", py_upsample,  METH_VARARGS},
  {"scale", py_scale,  METH_VARARGS},
  {NULL, NULL}
};

void initpcm(void) {
  (void) Py_InitModule("pcm", pcm_methods);
}
