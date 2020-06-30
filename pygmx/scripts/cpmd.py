# This is part of MiMiCPy

"""

This module contains the Section, Atom and Input classes that
allows for pythonic creation/manipulation of CPMD scripts

"""

from collections import OrderedDict 
import re
from itertools import chain
import pandas as pd
from .base import Script
from ..utils.strs import clean
from ..utils.constants import bohr_rad
from .._global import _Global as _global
from ..parsers.mpt import MPT
from ..parsers import pdb

class Section(Script):
   
    def __str__(self):
        
        val = ''
        
        for d in self.params():
            if getattr(self, d) == None:
                continue
            
            d_ = d.replace('_','-').replace('--', ' ').upper()
            v = str(getattr(self, d)).strip()
            if v == '':
                val += d_+'\n'
            else:
                val += f"{d_}\n{v}\n"
        
        return val
    
    @staticmethod
    def _chknumeric(s):
        splt = s.split()
        
        if len(splt) == 1:
            return s.replace('.','').replace('-','').isnumeric()
        else:
            for i in splt:
                if not Section._chknumeric(i):
                    return False
            return True

    @classmethod
    def fromText(cls, text):  
        i = 0
        section = cls()
        splt = text.splitlines()
        
        while i < len(splt)-1:
            if splt[i] == 'PATHS':
                setattr(section, splt[i], "\n".join(splt[i+1:i+3]))
                i += 2
                
            elif splt[i] == 'OVERLAPS':
                no = int(splt[i+1])
                ov = "\n".join(splt[i+1:i+no+2])
                setattr(section, splt[i], ov)
                
                i += no+1

            elif Section._chknumeric(splt[i+1]):
                setattr(section, splt[i], splt[i+1])
                
            elif not Section._chknumeric(splt[i]):
                setattr(section, splt[i], '')
                
            i += 1
        return section
    
class Atom:
    def __init__(self, coords=[], lmax='s', pp='MT_BLYP', labels=''):
        self.coords = coords
        self.pp = pp
        self.labels = labels
        self.lmax = lmax
    
    def __str__(self):
        if not self.pp.startswith('_'): self.pp = '_' + self.pp
        if not self.labels.startswith(' ') and self.labels != '': self.labels = ' ' + self.labels
        val = f'{self.pp}{self.labels}\n'
        val += f'   LMAX={self.lmax.upper()}\n'
        val += f'    {len(self.coords)}\n'
        for d in self.coords:
            val += f'  {d[0]}   {d[1]}   {d[2]}\n'
        val += '\n'
        return val
    
    @classmethod
    def fromText(cls, text, pp='MT_BLYP', labels=''):
        lmax = re.findall('LMAX=(.*)', text)[0]
        coords = [i.split() for i in text.splitlines()[2:]]
        return cls(coords, lmax, pp, labels)
    
class Input(Script):
    def __init__(self, *args):
        super().__init__()
        for val in args:
            setattr(self, val, Section())
        self.atoms = OrderedDict()
        self.info = 'MiMiC Run'
        self._ndx = None
    
    def checkSection(self, section):
        return self.hasparam(section)
    
    def __str__(self):
        val = ''
        
        for d in self.params():
            if getattr(self, d) == None:
                continue
            elif d.upper() == 'INFO':
                info = f'\n&INFO\n{getattr(self, d)}\nGENERATED BY MIMICPY\n&END\n'
            elif d.upper() == 'ATOMS':
                atoms = '\n&ATOMS\n'
                for k, v in getattr(self, d).items():
                    # link atoms are marked with astericks, like C*, in prepare.QM
                    atoms += f'*{k.replace("*", "")}{str(v)}'
                atoms += '&END\n'
            else:
                v = str(getattr(self, d))
                val += f"\n&{d.upper()}\n{v}&END\n"
        
        return info+val+atoms
    
    @classmethod
    def fromText(cls, text):
         text = clean(text)
         section_reg = re.compile(r'\&(.*?)\n((?:.+\n)+?)\s*(?:\&END)')
         sections = section_reg.findall(text)
         
         inp = cls()
         
         for k,v in sections:
             if k == 'INFO': setattr(inp, k, v.replace('GENERATED BY MIMICPY', ''))
             elif k == 'ATOMS':
                 atom_txt = re.compile(r'(\w+?)\n((?:.+\n)+?)(?:\*|$)').findall(v)
                 for atom, a_txt in atom_txt:
                     atom_symb = atom.split('_', 1)[0]
                     pp = atom.split('_', 1)[1].split()[0]
                     label = atom.replace(f"{atom_symb}_{pp}", '')
                     
                     inp.atoms[atom.split('_')[0]] = Atom.fromText(a_txt, pp, label)
                     
             else: setattr(inp, k, Section.fromText(v))
         
         
         return inp
     
    def toCoords(self, mpt, out):
        ext = out.split('.')[-1].lower()
        
        ids = [int(i.split()[1]) for i in self.mimic.overlaps.splitlines()[1:]]
    
        coords = list(chain.from_iterable(v.coords for k,v in self.atoms.items()))
        
        cpmd_coords = pd.DataFrame(coords)
        cpmd_coords.columns = ['x', 'y', 'z']
        
        if ext == 'pdb':
            # convert to ang
            cpmd_coords = cpmd_coords.applymap(lambda a: float(a)*bohr_rad*10)
        elif ext == 'gro':
            # convert to nm
            cpmd_coords = cpmd_coords.applymap(lambda a: float(a)*bohr_rad)
        
        cpmd_coords['id'] = ids
        
        if not isinstance(mpt, MPT): mpt = MPT.fromFile(mpt)
        mpt_coords = mpt[ids].merge(cpmd_coords, left_on='id', right_on='id').set_index(['id'])
        
        if ext == 'pdb':
            out_txt = pdb.writeFile(mpt_coords)
        elif ext == 'gro':
            pass
        
        _global.host.write(out_txt, out)