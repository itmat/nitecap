let pathways = [{name:"KEGG_GLYCOLYSIS_GLUCONEOGENESIS",
    url:"http://www.broadinstitute.org/gsea/msigdb/cards/KEGG_GLYCOLYSIS_GLUCONEOGENESIS",
    genes: ['ACSS2', 'GCK', 'PGK2', 'PGK1', 'PDHB', 'PDHA1', 'PDHA2', 'PGM2', 'TPI1', 'ACSS1', 'FBP1', 'ADH1B', 'HK2', 'ADH1C', 'HK1', 'HK3', 'ADH4', 'PGAM2', 'ADH5', 'PGAM1', 'ADH1A', 'ALDOC', 'ALDH7A1', 'LDHAL6B', 'PKLR', 'LDHAL6A', 'ENO1', 'PKM2', 'PFKP', 'BPGM', 'PCK2', 'PCK1', 'ALDH1B1', 'ALDH2', 'ALDH3A1', 'AKR1A1', 'FBP2', 'PFKM', 'PFKL', 'LDHC', 'GAPDH', 'ENO3', 'ENO2', 'PGAM4', 'ADH7', 'ADH6', 'LDHB', 'ALDH1A3', 'ALDH3B1', 'ALDH3B2', 'ALDH9A1', 'ALDH3A2', 'GALM', 'ALDOA', 'DLD', 'DLAT', 'ALDOB', 'G6PC2', 'LDHA', 'G6PC', 'PGM1', 'GPI']
    },
];


let factorials = [1, 1];
function factorial(k) {
    // Memoized factorial function for small k
    if (k <= 1) { return 1; }
    if (factorials[k] !== undefined)  { return factorials[k]; }

    factorials[k] = factorial(k-1) * k;
    return factorials[k];
}

let log_factorials = [0, 0];
function log_factorial(k) {
    if (k < 100) {
        if (log_factorials[k] === undefined) { log_factorials[k] = log_factorial(k-1) + Math.log(k); }
        return log_factorials[k];
    }
    // Stirlings approximation for large k
    return k * Math.log(k) - k + Math.log(2 * Math.PI * k) / 2;
}

function log_choose(n,k) {
    // log (n choose k) 
    return log_factorial(n) - log_factorial(n-k) - log_factorial(k);
}

function hypergeometric_prob(background_size, set_size, sample_size, intersection_size) {
    let log_p = log_choose(set_size,  intersection_size) + log_choose(background_size - set_size, sample_size - intersection_size) - log_choose(background_size, sample_size);
    return Math.exp(log_p);
}

function hypergeometric_test(background_size, set_size, sample_size, intersection_size) {
    // Probability of getting at least `intersection_size` under random sampling
    let p = 0;
    for (let k = intersection_size; k <= sample_size; k++) {
        p += hypergeometric_prob(background_size, set_size, sample_size, k);
    }
    return p;
}
