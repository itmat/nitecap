# nitecap
Non-parametric method for identification of circadian behavior

The main functionality is in nitecap.py with the nitecap() function providing a simple interface.

```python
from nitecap import nitecap
# 6 timepoints, each with 2 replicates. Data is grouped with replicates together and
data = [[5,6, 10,11, 20,21, 15,16,  8, 9, 2,1], # A very cyclic gene with low variance between samples
        [5,9, 10, 4, 20,15,  2, 1, 10,12, 1,5]] # A non-cyclic gene with higher variance between samples
q, td = nitecap(data, timepoints_per_cycle = 6,  num_replicates = 2, num_cycles = 1)
# q gives the q-values of the two genes
# td gives the "total_delta" test statistic for each gene (lower is more cyclic)
```
