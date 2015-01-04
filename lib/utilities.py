# Created on Tue Dec 23 21:15:19 2014

# Author: XiaoTao Wang
# Organization: HuaZhong Agricultural University

import logging
import numpy as np
from hiclib.fragmentHiC import HiCdataset
from mirnylib.numutils import fasterBooleanIndexing

log = logging.getLogger(__name__)

# A customized HiCdataset class, which makes filtering processes more flexible
class cHiCdataset(HiCdataset):
    
    def parseInputData(self, dictLike, commandArgs, **kwargs):
        '''
        Added Parameters
        ----------------
        commandArgs : NameSpace
            A NameSpace object defined by argparse.            
        '''
        ## Necessary Modules
        import numexpr
        # Simply load merged data
        self.merge([dictLike])
        # Total Reads
        self.trackLen = len(self.chrms1)
        
        self.metadata["100_TotalReads"] = self.trackLen
        self.metadata["152_removedUnusedChromosomes"] = self.trackLen - self.N
        self.metadata["150_ReadsWithoutUnusedChromosomes"] = self.N
        
        DSmask = (self.chrms1 >= 0) * (self.chrms2 >= 0)
        self.metadata["200_totalDSReads"] = DSmask.sum()
        self.metadata["201_DS+SS"] = len(DSmask)
        self.metadata["202_SSReadsRemoved"] = len(DSmask) - DSmask.sum()
        
        mask = DSmask
        
        ## Information based on restriction fragments
        sameFragMask = self.evaluate("a = (fragids1 == fragids2)",
                                     ["fragids1", "fragids2"]) * DSmask
        cutDifs = self.cuts2[sameFragMask] > self.cuts1[sameFragMask]
        s1 = self.strands1[sameFragMask]
        s2 = self.strands2[sameFragMask]
        SSDE = (s1 != s2)
        SS = SSDE * (cutDifs == s2)
        Dangling = SSDE & (~SS)
        SS_N = SS.sum()
        SSDE_N = SSDE.sum()
        sameFrag_N = sameFragMask.sum()
        
        dist = self.evaluate("a = - cuts1 * (2 * strands1 -1) - "
                             "cuts2 * (2 * strands2 - 1)",
                             ["cuts1", "cuts2", "strands1", "strands2"])
        Dangling_L = dist[sameFragMask][Dangling]
        library_L = int(np.ceil((np.percentile(Dangling_L, 95))))
        self.maximumMoleculeLength = library_L
        
        readsMolecules = self.evaluate(
            "a = numexpr.evaluate('(chrms1 == chrms2) & (strands1 != strands2) &  (dist >=0) &"
            " (dist <= maximumMoleculeLength)')",
            internalVariables=["chrms1", "chrms2", "strands1", "strands2"],
            externalVariables={"dist": dist},
            constants={"maximumMoleculeLength": self.maximumMoleculeLength, "numexpr": numexpr})
        
        if commandArgs.sameFragments:
            log.log(21, 'Removing read pairs located in the same restriction fragments ...')            
            mask *= (-sameFragMask)
            noSameFrag = mask.sum()
            self.metadata["210_sameFragmentReadsRemoved"] = sameFrag_N
            self.metadata["212_Self-Circles"] = SS_N
            self.metadata["214_DandlingEnds"] = SSDE_N - SS_N
            self.metadata["216_error"] = sameFrag_N - SSDE_N
            mask *= (readsMolecules == False)
            extraDE = mask.sum()
            self.metadata["220_extraDandlingEndsRemoved"] = -extraDE + noSameFrag
            log.log(21, 'Done!')
            
        if commandArgs.RandomBreaks:
            log.log(21, 'Determined Hi-C library size: ' + str(library_L))
            log.log(21, 'Removing "Random Breaks" ...')
            
            ini_N = mask.sum()
            mask *= ((self.dists1 + self.dists2) <= library_L)
            rb_N = ini_N - mask.sum()
            self.metadata["330_removeRandomBreaks"] = rb_N
            
            logging.log(21, 'Done!')
        
        if mask.sum() == 0:
            raise Exception(
                'No reads left after filtering. Please, check the input data')
            
        del DSmask, sameFragMask
        del dist, readsMolecules
        
        self.metadata["300_ValidPairs"] = self.N
        
        self.maskFilter(mask)
    
    def maskFilter(self, mask):
        """
        Use numpy's internal mask mechanism when OverflowError occurs.

        Parameters
        ----------
        mask : array of bools
            Indexes of reads to keep
            
        """
        # Uses 16 bytes per read
        length = 0
        ms = mask.sum()
        
        assert mask.dtype == np.bool
        
        self.N = ms
        self.DSnum = self.N
        
        if hasattr(self, "ufragments"):
            del self.ufragmentlen, self.ufragments
            
        for name in self.vectors:
            data = self._getData(name)
            ld = len(data)
            if length == 0:
                length = ld
            else:
                if ld != length:
                    self.delete()
            try:
                # see mirnylib.numutils
                newdata = fasterBooleanIndexing(data, mask, outLen = ms,
                                                bounds = False)
            except OverflowError:
                newdata = data[mask]
                
            del data
            
            self._setData(name, newdata)
            
            del newdata
            
        del mask
        
        self.rebuildFragments()
