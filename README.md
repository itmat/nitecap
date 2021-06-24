# Nitecap

Explore, analyze, and share high-throughput omics circadian datasets through an easy-to-use <a href="https://nitecap.org">web interface</a>.

<p align="center" style="padding: 0em;"> 
  <img src="src/server/static/images/slides.gif" alt="Sample signal">
</p>

<b><a href="https://nitecap.org">Nitecap</a></b> is an exploratory circadian data analysis tool aimed at high-throughput omics data. It provides a web-interface to examine your dataset with highly-responsive visualizations, allowing the easy viewing of hundreds or thousands of genes or other features. Nitecap computes some standard rhythmicity tests for you, including JTK, ARSER, Lomb-Scargle, Cosinor, and several tests to compare differential rhythmicity across two conditions (such as phase differences).

<br/>

## Implementation
<a href="https://nitecap.org">Nitecap.org</a> consists of a web server and a serverless computational backend. Algorithms such as JTK, ARSER, and Lomb-Scargle which require substantial computation time are mostly run in the serverless backend, while others are run on the server and in the user's web browser.<br />

### 1. Computational backend
Algorithms are executed in Lambda functions which are written in Python. Algorithms written in R are executed using rpy2, an interface to R running embedded in a Python process. The code for the computational backend and algorithms can be found in the <code>src/computation</code> directory. Note that some algorithms are still part of the server.
<br />

### 2. Server
The server is imagined as a containerized application. The code for the server resides in the <code>src/server</code> directory.
<br />
### 3. Infrastructure
The infrastructure is specified in TypeScript using AWS Cloud Development Kit (CDK). The code describing infrastructure can be found in the <code>lib</code> directory.

<br />

## Contributions and support

Nitecap is developed at the <a href="http://bioinf.itmat.upenn.edu/">Institute for Translational Medicine and Therapeutics Bioinformatics, University of Pennsylvania</a>. For any questions or comments, feel free to contact us by email <a href="mailto:admins@nitecap.org">admins@nitecap.org</a>.

<br />

## License

GNU General Public License, version 3
