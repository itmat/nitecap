# main Functions to access Umbrella and hewitt test R hythmic A
# nalysis I ncoorperating N on-parametric methods Author: Thaben


#' Detection of rhythmic behavior in time series.
#' 
#' rain detects rhythms in time-series using non parametric methods.
#' It uses an extension of the rank test for Umbrella Alternatives 
#' (Mack & Wolfe, 1981), based on on the Jonckheere-Terpstra test, which tests
#' whether sets of groups have a trend or not.  The Umbrella method extends 
#' this to independent rising and falling sets.
#' @param x numeric array, containing the data. One row per time point, 
#' one column per sample. If more than one replicate is done, see 
#' nr.series for formatting.
#' @param deltat numeric: sampling interval. 
#' @param period numeric: Period to search for. 
#' The given period is mapped to the best matching number of measurements. 
#' A set of periods can be defined by period and period.delta.
#' @param period.delta numeric: width of period interval. 
#' A interval of different period-length to evaluate is defined by 
#' period $-$ period.delta and period $+$ period.delta. 
#' In this interval all possible numbers of time points according to the 
#' deltat are tested.
#' @param peak.border vector c(min,max): defines the different form of the 
#' peak. min and max have to be >0 and <1. The concrete interpretation depends
#' on the chosen method (see Details). (default = c(0.3,0.7))
#' @param nr.series numeric: Number of replicates of the whole time series. 
#' If using nr.series all series have to have the same length. 
#' These multiple time series contained in x must be organized timepoint by 
#' timepoint using the following format 
#' [r1t1, r2t1, r1t2, r2t2, ..., r1tn, r2tn] 
#' where ritj is the i'th repeat of the j'th time-point. 
#' @param measure.sequence numeric array: Numbers of replicates for each time
#' point. 
#' By using 'measure.sequence', irregular time courses may be evaluated.
#' A value of 0 is possible and handeled correctly. The array determines how 
#' many values are present for each time piont. 
#' The values are ordered in the same format as specified above. 
#' measure.sequence overwrites nr.series if both are set.
#' @param method string ('independent', 'longitudinal'): identify the method
#' to use (see Details).
#' @param na.rm boolean: calculate individual statistics for time series 
#' containign NAs. The time series of a sample containing NAs is treated
#' as if the time points with NA are not measured. Using this option increases 
#' calculation time.
#' @param adjp.method string (see \code{\link[multtest]{mt.rawp2adjp}}): 
#' select the method wich is used for the multiple testing correction for the 
#' different phases and periods and shapes tested
#' @param verbose status output
#' @return An array containing p-values and the description of the best
#' matching model. 
#' Each row apply to a sample in x.
#'    \item{pVal }{The p-Values}
#'    \item{phase }{The phase of the peak (see Details)}
#'    \item{peak.shape }{The shape of the curve depending on the method used
#'    (see Details)}
#'    \item{period }{The period length, same unit as deltat}
#' @details 
#' The method tests whether a the time course consists of alternating rising 
#' and falling slopes, repeated with a distinct period. The partitions of the 
#' rising part with respect to the whole period are given by 
#' peak.border = c(min, max). The value peak.shape specifies this partition in 
#' the best matching model. The phase is defined as the time point with the 
#' peak. There are two versions of umbrella:
#' \describe{
#' \item{independent}{Multiple periods are interpreted as repeats of one 
#' period.}
#' \item{logitudinal}{The whole time series remains unaffected. Partial slopes
#' in the beginning and end of the time series are evaluated as shorter 
#' slopes. This method implicitly rejects underlying trends.This should be 
#' used only with longitudinal samples, hat may contain strong trends}
#' }
#' @author Paul F. Thaben
#' @references 
#' Mack, G. A., & Wolfe, D. A. (1981). K-Sample Rank Tests for Umbrella
#' Alternatives. 
#' \emph{Journal of the American Statistical Association},
#' \bold{76(373)}, 175--181.
#' 
#' @examples 
#' # create a dataset with different noise levels
#' noise.levels <- c(1, 0.5, 0.2, 0.1, 0.05, 0.02)
#' period <- 15
#' testset <- apply(matrix(noise.levels, nrow = 1), 2, function(noise){
#'    timecourse = 1 + 0.4 * cos((1:30) / period * 2 * pi) + 
#'    rnorm(30, 0, noise)
#' })
#' 
#' 
#' results <- rain(testset, period=15, deltat=1, method='independent')
#' 
#' plot(-log(results$pVal) ~ noise.levels)
#' 
#' \dontrun{
#' # testing a biological dataset
#' data(menetRNASeqMouseLiver) 
#' menet.ossc <- rain(t( menetRNASeqMouseLiver ), deltat = 4, period = 24, 
#'    nr.series = 2, peak.border = c(0.3, 0.7), verbose=TRUE)
#' require('lattice')
#' 
#' best <- order(results$pVal)[1:10]
#' 
#' xyplot(as.matrix(menetRNASeqMouseLiver
#'    [best, (0:5 * 2 + rep(c(1, 2), each = 6))]) 
#'  ~rep(0:11 * 4 + 2, each = 10) |rownames(menetRNASeqMouseLiver)[best], 
#'  scales = list(y = list(relation = 'free')),
#'  layout = c(2, 5), type = 'b', pch = 16, xlab = 'time', 
#'  ylab = 'expression value', cex.lab = 1)
#' 
#' }
#' @keywords Statistics|nonparametric Statistics|ts
#' @export
rain <- function(x, deltat, period, period.delta = 0, peak.border = c(0.3, 
    0.7), nr.series = 1, measure.sequence = NULL, method = "independent", 
    na.rm = FALSE, adjp.method = "ABH", verbose = getOption("verbose")) {
    
    # catch one dimensional vectors as interpreting them as one time
    # course
    if (is.null(dim(x))) 
        x <- matrix(x, ncol = 1)
    
    
    # create measure sequence if nessecary
    if (is.null(measure.sequence)) {
        measure.sequence = rep(nr.series, floor(nrow(x) / nr.series))
    }
    
    # check for correct data annotation
    if (!is.null(measure.sequence) && sum(measure.sequence) != nrow(x)) {
        stop("invalid annotation of time points")
    }
    
    # different behaviour for na.rm
    if (na.rm) {
        # look for na
        valmasks <- apply(x, 2, is.na)
        
        # make a list of the measurement sequence, for each sample column
        # (NA's are removed)
        seqLists <- apply(valmasks, 2, reduceByNA, mseq = measure.sequence)
        
        # get a List of unique measurement sequences occuring in Dataset
        codes <- apply(seqLists, 2, paste, collapse = "")
        uniqcode <- unique(codes)
        
        # empty resultframe as spaceholder
        result <- data.frame(pVal = rep(NA, ncol(x)), phase = rep(NA, 
            ncol(x)), peak = rep(NA, ncol(x)), period = rep(NA, ncol(x)))
        
        per <- floor((period - period.delta) / deltat):ceiling((period + 
            period.delta) / deltat)
        
        # some output
        if (verbose) {
            message("\r\ndeploying ", length(uniqcode), " statistics", 
                appendLF = TRUE)
            pb <- txtProgressBar(min = 0, max = ncol(x), style = 3, 
                width = 30)
        }
        counter = 0
        
        # go through all different variants of NA-Distributions
        for (code in uniqcode) {
            
            pos <- which(codes == code)
            counter = counter + length(pos)
            if (verbose) 
                setTxtProgressBar(pb, counter)
            
            subSet <- x[, pos]
            
            # if subset contains only 1 series, the matrix has to be forced
            if (is.null(dim(subSet))) 
                subSet <- matrix(subSet, ncol = 1)
            
            #if no measurements are left repeat 'empty' results
            if (all(is.na(subSet))) {
                len = ncol(subSet)
                result[pos, ] <- data.frame(pVal = rep(1, len), 
                    phase = rep(0, len), peak = rep(0, len), 
                    period = rep(period/deltat, len))
                next
            }
            
            # shrink the test set by removing the NA values
            subSet <- apply(subSet, 2, function(x) {
                x[!is.na(x)]
            })
            if (is.null(dim(subSet))) 
                subSet <- matrix(subSet, nrow = 1)
            
            # use the measure.sequence without the NA-measurements
            sub.measure.sequence <- seqLists[, pos[1]]
            
            # run rain
            if (method %in% c("umb1", "longitudinal")) {
                part.result <- umbrellaCirc(subSet, nr.series = 1, 
                    per, peak.border, type = 1, adjp.method = adjp.method, 
                    sub.measure.sequence, verbose = FALSE)
            }
            if (method == "umb2") {
                part.result <- umbrellaCirc(subSet, nr.series = 1, 
                    per, peak.border, type = 2, adjp.method = adjp.method, 
                    sub.measure.sequence, verbose = FALSE)
            }
            if (method %in% c("umb3", "independent")) {
                part.result <- umbrellaCirc(subSet, nr.series = 1, 
                    per, peak.border, type = 3, adjp.method = adjp.method, 
                    sub.measure.sequence, verbose = FALSE)
            }
            
            # save the results in the result table
            result[pos, ] <- part.result
        }
    } else {
        # run rain in the choosen format
        if (method %in% c("umb1", "longitudinal")) {
            per <- floor((period - period.delta) / deltat):ceiling((period + 
                period.delta) / deltat)
            result <- umbrellaCirc(x, nr.series = 1, per, peak.border, 
                type = 1, adjp.method = adjp.method, measure.sequence, 
                verbose = verbose)
        }
        if (method == "umb2") {
            per <- floor((period - period.delta) / deltat):ceiling((period + 
                period.delta) / deltat)
            result <- umbrellaCirc(x, nr.series = 1, per, peak.border, 
                type = 2, adjp.method = adjp.method, measure.sequence, 
                verbose = verbose)
        }
        if (method %in% c("umb3", "independent")) {
            per <- floor((period - period.delta) / deltat):ceiling((period + 
                period.delta) / deltat)
            result <- umbrellaCirc(x, nr.series = 1, per, peak.border, 
                type = 3, adjp.method = adjp.method, measure.sequence, 
                verbose = verbose)
        }
    }
    
    colnames(result)[3] <- "peak.shape"
    result["phase"] <- result["phase"] * deltat
    result["period"] <- result["period"] * deltat
    result["peak.shape"] <- result["peak.shape"] * deltat
    if (!is.null(colnames(x))) 
        rownames(result) <- make.unique(colnames(x))
    return(result)
}


reduceByNA <- function(valmask, mseq) {
    valmask <- ifelse(valmask, 0, 1)
    apply(rbind(cumsum(mseq) - mseq + 1, cumsum(mseq)), 2, function(coord) {
        if (coord[1] <= coord[2] & coord[2] > 0) {
            return(sum(valmask[coord[1]:coord[2]]))
        } else {
            return(0)
        }
    })
} 
# Main Function of the rain algorithm Author: thaben

#' String based code for distinct model settings
#' 
#' @param sequence sequence of measurement groups
#' @param extremas index of extremas
#' @param cycl boolean: statistic treats cyclic arrangement of samples
#' differently
#' @return code string
#' @noRd 
#' 
#' @author thaben
generateCode <- function(sequence, extremas, cycl = FALSE) {
    
    # different behavoiur for cyclic tests
    if (cycl & length(extremas) == 1 & extremas[1] != 1) {
        l <- extremas
        
        # seperate the inflections
        words <- sapply(list(sequence[1], sequence[l]), function(i) {
            paste(sort(i), ".", sep = "", collapse = "")
        })
        # part between start and inflection
        if (l > 2) {
            words <- c(words, paste(sort(sequence[2:(l - 1)]), collapse = "."))
        }
        # part between inflection and end
        if (l < length(sequence) - 1) {
            words <- c(words, paste(sort(sequence[(l + 1):(length(sequence) - 
                1)]), collapse = "."))
        }
        # collapse and return
        return(paste(sort(words), collapse = " "))
    }
    # write valid list of extremas
    ex <- c(1, extremas[extremas > 1 & extremas < length(sequence)], 
        length(sequence))
    # generate contentStrings for each slope
    words <- sapply(2:length(ex), function(i) {
        paste(sort(sequence[ex[i - 1]:ex[i]]), collapse = ".")
    })
    # sort slopes and combine them
    return(paste(sort(words), collapse = " "))
}

#' Search for rhytrhmicities by using umbrella alternatives
#' 
#' use rain() to access this function
#' @inheritParams rain
#' @param tSer numeric array; one row per time point, one colum per object of 
#' evaluation 
#' @param periods numeric array list of periods to lookup. 
#' @param peaks borders of peak shape
#' @param type numeric index of detection method
#' @return data frame containing best mtching phase, period, 
#' paek-shape and pValue
#' 
#' @noRd
#' @author thaben
#' @import gmp
#' @import multtest

hardings <- list()
decoder <- data.frame(code = "null", harding = 0)

umbrellaCirc <- function(tSer, nr.series = 1, periods = c(nrow(tSer)), 
    peaks = c(0.35, 0.65), type = 1, adjp.method, measure.sequence, 
    verbose = TRUE) {
    
    # preparing lists
    if (is.null(measure.sequence)) {
        tp <- nrow(tSer) / nr.series
        measure.sequence <- rep(nr.series, tp)
    } else {
        tp <- length(measure.sequence)
    }
    peakpos <- c()
    relpeak <- c()
    periodlist <- c()
    test.cases <- 0
    # hardings <- list()
    # decoder <- data.frame(code = "null", harding = 0)
    compmat <- list()
    distris <- c()
    
    # there are several ways to calculate the statistic and so
    # type = 1 is 'longitudinal' in the main function type = 3 is 'independent'
    # type = 2 is a deprecated in between solution. It is completely working, 
    # but the performance ist not good enugh to be public visible
    
    # in this part the comparison matrices, statistics and so on are prepared. 
    # Afterwards the time series are evaluated with these statistics
    
    # 'longitudinal'
    if (type == 1) {
        # extended min function to avoid warnings if running min on empty
        # list
        emin <- function(x) {
            if (length(x) == 0) 
                return(Inf)
            return(min(x))
        }
        
        #prepare some additional lists
        ups <- c()
        extremas <- list()
        
        #go through all periods to measure
        for (period in periods) {
            maxtp <- ceiling(tp / period) * period
            
            # specify how the assymmetric scale peaks[] translates in this 
            # period setting
            perpeaks <- (floor(peaks[1] * period)):(ceiling(peaks[2] * 
                period))
            perpeaks <- perpeaks[perpeaks > 0 & perpeaks < period - 
                1]
            
            # the list of peakpositions for all phases and peak shapes under 
            # this period length is prepared
            peakl <- matrix(nrow = period * length(perpeaks), ncol = 1)
            peakl[, 1] <- rep(1:period, each = length(perpeaks))
            peakl <- lapply(peakl[, 1], seq, to = maxtp, by = period)
            
            # specify all peaks and troughs for all phases and peak shapes
            perpeakpos <- rep(1:period, each = length(perpeaks))
            peakpos <- c(peakpos, perpeakpos)
            perrelpeak <- rep(perpeaks, period)
            relpeak <- c(relpeak, perrelpeak)
            
            trough <- lapply(1:length(peakl), function(x) {
                peakl[[x]] + perrelpeak[[x]]
            })
            
            peakl <- lapply(peakl, function(x) {
                y = x %% maxtp
                return(y[y > 1 & y < tp])
            })
            
            trough <- lapply(trough, function(x) {
                y = x %% maxtp
                return(y[y > 1 & y < tp])
            })
            
            # check whether a peak or a trough comes first to evaluate if the
            # modell first rises or falls
            perups <- apply(rbind(sapply(peakl, emin), sapply(trough, 
                emin)), 2, function(v) {
                v[1] <= v[2]
            })
            ups <- c(perups, ups)
            
            # write it to the global exrtremas list
            periodlist <- c(periodlist, rep(period, length(perups)))
            extremas <- c(extremas, lapply(1:length(peakl), function(x) {
                sort(unique(c(peakl[[x]], trough[[x]])))
            }))
        }
        
        # filter out results without any peak or trough to avoid
        # meaningless results
        filter <- sapply(extremas, function(val) {
            length(val) != 0
        })
        ups <- ups[filter]
        periodlist <- periodlist[filter]
        extremas <- extremas[which(filter)]
        peakpos <- peakpos[filter]
        relpeak <- relpeak[filter]
        
        test.cases <- length(ups)
        
        trials <- measure.sequence
        
        coordtable <- rbind(c(1, cumsum(measure.sequence)[-tp] + 1), 
            cumsum(measure.sequence))
        
        # preparing the compare matrices for all different settings
        compmat <- lapply(1:test.cases, function(i) {
            manWilcoxMatrix(coords = lapply(c(1:tp), function(x) {
                if (coordtable[1, x] > coordtable[2, x]) 
                    return(c())
                coordtable[1, x]:coordtable[2, x]
            }), l = extremas[[i]], up = ups[i])
        })
        
        if (verbose) 
            message("\r\ncalculating distributions (", test.cases, 
                "):", appendLF = FALSE)
        distris <- numeric(test.cases)
        
        # calculate the statistics for all settings. To save computation time
        # the function generate code is used to check for similar previos 
        # calculated statistics
        for (i in 1:test.cases) {
            code <- generateCode(trials, extremas[[i]])
            
            ## cat(code,'\r\n')
            if (code %in% decoder$code) {
                if (verbose) message(".", appendLF = FALSE)
                pos <- which(decoder$code == code)
                distris[i] <- (decoder$harding[pos])
            } else {
                if (verbose) message("*", appendLF = FALSE)
                hardingpos <- length(hardings) + 1
                decoder <- rbind(decoder, data.frame(code = code, 
                    harding = hardingpos))
                hardings[[hardingpos]] <- harding(trials, extremas[[i]])$pval
                distris[i] <- (hardingpos)
            }
        }
        if (verbose) 
            message("\r\nDone")
    }
    
    # deprecated version 
    if (type == 2) {
        # new lists
        extremas <- list()
        sequences <- list()
        runind <- 1
        for (period in periods) {
            
            # prepare the coordtables and check which time points are repeats 
            # of others for a given period
            use.pers <- max(floor(tp/period), 1)
            perpeaks <- (floor(peaks[1] * period)):(ceiling(peaks[2] * 
                period))
            perpeaks <- perpeaks[perpeaks > 0 & perpeaks < period]
            coordtable <- rbind(c(1, cumsum(measure.sequence)[-tp] + 
                1), cumsum(measure.sequence))
            coords <- lapply(1:(period * use.pers), function(i) {
                if (i > tp) 
                    return(NULL)
                l <- do.call(c, lapply(seq(i, tp, period * use.pers), 
                    function(x) {
                        if (coordtable[1, x] > coordtable[2, x]) 
                            return(c())
                        return(coordtable[1, x]:coordtable[2, x])
                    }))
                return(l)
            })
            
            # generate the comparisonmatrices for a setting 
            group.size <- sapply(coords, length)
            for (phase in 1:period) {
                maxs <- seq(phase, period * use.pers, period)
                perextremas <- lapply(perpeaks, function(peak) {
                    mins <- (maxs + peak - 1)%%(period * use.pers) + 1
                    return(c(mins, maxs))
                })
                percompmat <- lapply(perextremas, function(extremlist) {
                    split <- extremlist[1]
                    extremlist <- sort((extremlist + 1 - split)%%(period * 
                        use.pers))
                    rotmat <- c(split:(period * use.pers), 1:(split - 1)
                        )[1:(period * use.pers)]
                    manWilcoxMatrix(coords = coords[rotmat], l = extremlist, 
                        up = TRUE)
                })
                
                peakpos <- c(peakpos, rep(phase, length(perpeaks)))
                relpeak <- c(relpeak, perpeaks)
                compmat <- c(compmat, percompmat)
                extremas <- c(extremas, lapply(perextremas, 
                    function(extremlist) {
                        split <- extremlist[1]
                        extremlist <- sort((extremlist + 1 - split) %% 
                            (period * use.pers))
                        
                    }
                ))
                
                periodlist <- c(periodlist, rep(period, length(percompmat)))
                sequences <- c(sequences, lapply(perextremas, 
                    function(extremlist) {
                        split <- extremlist[1]
                        rotmat <- c(split:(period * use.pers), 
                                    1:(split - 1))[1:(period * use.pers)]
                        return(group.size[rotmat])
                    }
                ))
            }
        }
        
        test.cases <- length(compmat)
        
        # calculate the statistics reuse similar statistics
        if (verbose) 
            message("\r\ncalculating distributions (", test.cases, 
                "):", appendLF = FALSE)
        distris <- numeric(test.cases)
        for (i in 1:test.cases) {
            code <- generateCode(sequences[[i]], extremas[[i]])
            if (code %in% decoder$code) {
                if (verbose) 
                    message(".", appendLF = FALSE)
                pos <- which(decoder$code == code)
                distris[i] <- (decoder$harding[pos])
            } else {
                if (verbose) 
                    message("*", appendLF = FALSE)
                hardingpos <- length(hardings) + 1
                decoder <- rbind(decoder, data.frame(code = code, 
                    harding = hardingpos))
                hardings[[hardingpos]] <- harding(sequences[[i]], 
                    extremas[[i]])$pval
                distris[i] <- (hardingpos)
            }
        }
        
        if (verbose) 
            message("\r\nDone")
        
    }
    
    # rain3 combine all datapoints in one circular Umbrella
    if (type == 3) {
        
        extremas <- list()
        sequences <- list()
        
        for (period in periods) {
            
            # for each period define the position of the peak
            perpeaks <- c((ceiling((1 - peaks[1]) * period)):(floor((1 - 
                peaks[2]) * period)))
            perpeaks <- perpeaks[perpeaks > 0 & perpeaks < period]
            
            # coordtable holds the beginning and ending index for each
            # timepoint
            coordtable <- rbind(c(1, cumsum(measure.sequence)[-tp] + 
                1), cumsum(measure.sequence))
            
            # for each phase setup the frames
            for (phase in 1:period) {
                
                # arrange the groups so that peak is at the first point and 
                # each group contains all measurement
                coordlists <- lapply(phase:(phase + period), function(i) {
                    i <- ((i - 1) %% period) + 1
                    if (i > tp) 
                        return(NULL)
                    l <- do.call(c, lapply(seq(i, tp, period), function(x) {
                        if (coordtable[1, x] > coordtable[2, x]) {
                            return(c())
                        }
                        return(coordtable[1, x]:coordtable[2, x])
                    }
                    ))
                    return(l)
                })
                
                # generate comparison matrices
                percompmat <- lapply(perpeaks, function(peak) {
                    manWilcoxMatrix(coords = coordlists, l = peak + 
                        1, up = FALSE)
                })
                
                # write all to global setting tables peakposition
                peakpos <- c(peakpos, rep(phase, length(perpeaks)))
                # Number of points from peak to trough
                relpeak <- c(relpeak, perpeaks)
                # comparison matrices
                compmat <- c(compmat, percompmat)
                # period lengths
                periodlist <- c(periodlist, rep(period, length(percompmat)))
                # number of points in the slopes
                sequences <- c(sequences, lapply(perpeaks, function(x) {
                    sapply(coordlists, length)
                }))
            }
        }
        test.cases <- length(compmat)
        
        if (verbose) 
            message("\r\ncalculating distributions (", test.cases, 
                "):", appendLF = FALSE)
        
        distris <- numeric(test.cases)
        for (i in 1:test.cases) {
            # generate codestring to avoid repeated calculation of
            # distributions
            code <- generateCode(sequences[[i]], c(1 + relpeak[i]), 
                cycl = TRUE)
            
            # if code ist still present enter the right harding distribution
            # into the decoder list else make new distribution
            if (code %in% decoder$code) {
                if (verbose)
                    message(".", appendLF = FALSE)
                pos <- which(decoder$code == code)
                distris[i] <- (decoder$harding[pos])
            } else {
                if (verbose)
                    message("*", appendLF = FALSE)
                hardingpos <- length(hardings) + 1
                decoder <- rbind(decoder, data.frame(code = code, 
                    harding = hardingpos))
                hardings[[hardingpos]] <- harding(sequences[[i]], 
                    c(1 + relpeak[i]), cycl = TRUE)$pval
                distris[i] <- (hardingpos)
            }
        }
        if (verbose) 
            message("\r\nDone")
    }
    # end of generating Statistical distributions
    
    # evaluating the Dataset
    if (verbose)
        message("\r\nEvaluating Datasets: ")
    
    # preparing resulttables
    pVal <- numeric(ncol(tSer))
    phase <- numeric(ncol(tSer))
    peak <- numeric(ncol(tSer))
    period <- numeric(ncol(tSer))
    
    # progressBar
    if (verbose) 
        pb <- txtProgressBar(min = 0, max = ncol(tSer), style = 3, 
            width = 30)
    
    # adjust.p.method correction
    col.adjp.method <- ifelse(adjp.method == "TSBH", "TSBH_0.05", 
        adjp.method)
    # for each single time series
    for (ind in 1:ncol(tSer)) {
        # reset progressbar
        if (verbose) 
            setTxtProgressBar(pb, ind)
        
        # pick column
        list <- tSer[, ind]
        
        # create comparison matrix of real Data
        testcomp <- sign(sapply(list, function(x) {
            list - x
        }))
        testcomp[is.na(testcomp)] <- 0
        
        # compare this compMatrix, with the ones calculated for different
        # settings
        scores <- sapply(seq_len(test.cases), function(i) {
            resmat <- compmat[[i]] * testcomp
            return(sum(resmat[resmat > 0])/2)
        })
        
        # for these scores find theaccording p-Values
        pvals <- sapply(seq_len(test.cases), function(i) {
            p <- hardings[[distris[i]]][scores[i]]
            if (length(p) == 0) 
                return(1)
            return(p)
        })
        # bad-value protection
        pvals[scores == 0] <- 1
        
        # if no 'real' pValues could be detected give direct output to
        # avoid problems
        if (min(pvals) == max(pvals)) {
            pVal[ind] <- 1
            best <- 1
        } else {
            # pvalue adjustments
            adjusted <- suppressWarnings(mt.rawp2adjp(pvals, 
                proc = adjp.method))
            best <- adjusted$index[1]
            pVal[ind] <- adjusted$adjp[1, col.adjp.method]
            if (is.na(pVal[ind])) 
                pVal[ind] <- 1
            
        }
        # write measurement parameters to output tabels
        phase[ind] <- peakpos[best]
        peak[ind] <- relpeak[best]
        period[ind] <- periodlist[best]
    }
    if (verbose) 
        message("\r\nDone\r\n")
    # return all
    return(data.frame(pVal = pVal, phase = phase, peak = peak, 
        period = period))
} 
#' fuction to calculate the man wilcox sum of two sets
#' 
#' compares all elements of x with all elements of y counts up the result score
#' for each comparison, where elem(x) < elem(y)
#' @param x set of numeric 
#' @param y set of numeric
#' @return the score
#' 
#' @author thaben
#' @noRd
lcomp <- function(x, y) {
    
    return(sum(sapply(x, function(z) {
        sum(ifelse(y > z, 1, 0))
    })))

}

#' calculate the jonkheere terpstra statistic for a series of sets of numbers
#' 
#' @param list a list of vectors of numeric
#' @return the resulting jonkheere terpstra statistic
#' 
#' @author thaben
#' @noRd
manWilcox <- function(list) {
    num.sets <- length(list)
    
    # compare each set with the sets at later position in the list
    # sums up a series of man wilcox comparisons 
    u <- sum(sapply(c(1:(num.sets - 1)), function(i) {
        sum(sapply((i + 1):num.sets, function(x) lcomp(list[[i]], 
            list[[x]])))
    }))

    return(u)
}

#' Calculate Umbrella statistic from a series of numeric vectors
#' 
#' @param x list of numeric vectors
#' @param l set of inflections
#' @param up logical whether the series between the start and the first 
#' inflection is rising or falling
#' @return the statistic
#' 
#' @author thaben
#' @noRd
calcUmbrellaM <- function(x, l, up = TRUE) {
    len <- length(x)
    direcs = rep(c(-1, 1), len = length(l) + 2)
    
    lext = c(1, l[l < len & l > 1], len)
    
    if (up) 
        direcs = direcs[-1]
    Al <- sum(sapply(1:(length(lext) - 1), function(i) {
        vals = x[lext[i]:lext[i + 1]]
        if (direcs[i] == -1) vals = rev(vals)
        return(manWilcox(vals))
    }))
    return(Al)
}


#' Calculation of a matrix, allowing fast man wilcox tests
#'
#' returns a comparisonMatrix of should be results 1 := row > col, 0 :=
#' Not compared or equal, -1 := row < col
#' @param coords list of vectors of numbers depicting the coordinates in the 
#' input vector of samples. Each element of the list represents a set of 
#' grouped samples
#' @param l numeric vector: series of inflection 
#' @param up boolean: if the first part of the series (1..l[1]) is expected to
#' rise
#' @return returns a matrix give the expexted > or < relations in a 
#' sample matrix
#'
#' @author thaben
#' @noRd
manWilcoxMatrix <- function(coords, l, up = TRUE) {
    # count the number of sample sets
    len = length(coords)
    
    # estimate the number of time points
    tp = max(do.call(c, coords))
    
    # add the initial and last time to the series of inflections and sort
    ls = l[l > 1 & l < len]
    ls = sort(c(1, ls, len))
    
    # prepare resulting compare matrix
    comparematrix = matrix(rep(0, tp^2), nrow = tp)
    
    # two markers indicating if for the current part the data should rise or 
    # fall
    rowbiggercol = 1
    colbiggerrow = -1
    
    if (up) {
        rowbiggercol = -1
        colbiggerrow = 1
    }
    
    # go through the coords list by subsets of pure rising or falling series
    for (i in seq_len(length(ls) - 1)) {
        for (x in ls[i]:(ls[i + 1] - 1)) {
            for (y in (x + 1):(ls[i + 1])) {
                comparematrix[coords[[x]], coords[[y]]] = 
                    comparematrix[coords[[x]], coords[[y]]] + rowbiggercol
                comparematrix[coords[[y]], coords[[x]]] = 
                    comparematrix[coords[[y]], coords[[x]]] + colbiggerrow
            }
        }
        rowbiggercol = -rowbiggercol
        colbiggerrow = -colbiggerrow
    }
    comparematrix = sign(comparematrix)
    return(comparematrix)
} 
# Different Methods to estimate the Propability-distribution using
# R.GMP for 'Multiple Precision Arithmetic' Author: thaben
# library("gmp")

#' Folding arrays
#' 
#' computes multiplication of ploynomes from elements like (1-i^x)^n 
#' whith x e N and n e (+1,-1)
#' using gmp for exact numerics
#' @param arr array of polynomial coefficients
#' @param f number describing both indices. x <- abs(f) and n <- sign(f)
#' @param len length of arr
#' @return folding of the new element on the remaining array
#' 
#' @author thaben
#' @noRd
foldarr <- function(arr, f, len) {
    
    # decompose the information saved in f
    st <- abs(f)
    sig <- sign(f)
    
    # computation the to effect the series are skipped (should NEVER happen)
    if (st >= len) 
        return(arr)
    
    # seperate the cases sig = +1 and sig = -1
    if (sig == 1) {
        # construct an array where the initial array is shifted by st
        arrs <- matrix(c(as.bigz(rep(0, st)), arr[, 1:(len - st)]), 
            ncol = len)
        # and substract it
        arr2 <- arr - arrs
        return(arr2)
    } else {
        # this case is done by multiplication of a matrix (see Harding 
        # for details)
        seq <- c(1, rep(0, st - 1))
        mmat <- do.call("rbind", lapply(1:len, function(j) {
            c(rep(0, j - 1), rep(seq, len = len - j + 1))
        }))
        return(arr %*% mmat)
    }
}


# new version with l as a series of extrema

#' Exact Distributions 
#' 
#' Using the harding Procedure to generate exact Distributions for Umbrella 
#' and Rain Tests
#' @param mList List of group sizes 
#' @param l list of inflection points
#' @param cycl boolean: first point is a copy of the last one and has to be
#' treated specially. Is only evaluated if only one single inflection > 1 
#' is present. Parameter is meaningless without any inflection
#' @return list of pValues and the probability density
#' 
#' @author thaben
#' @noRd 
harding <- function(mList, l = NULL, cycl = FALSE) {
    
    len <- length(mList)
    N <- sum(mList)
    nvars <- 0
    maxval <- 0
    if (is.null(l)) {
        genfunc <- 1:N
        for (m in mList) {
            genfunc <- c(genfunc, -seq_len(m))
        }
        maxval <- (sum(mList)^2 - sum(mList^2))/2
    } else {
        # special treatment of statistic when a cyclic case is tested. In a
        # first step the first element is excluded and all variables are
        # adapted
        
        if (cycl && length(l) == 1 && l[1] != 1) {
            l <- l - 1
            special <- mList[1]
            mList <- mList[-1]
            len <- length(mList)
            N <- sum(mList)
        } else {
            cycl <- FALSE
            special <- 0
        }
        
        # very special case sometimes leeding to problems
        if(all(l == 1)){
            special <- 0
        }
        
        # including first and last positions
        lList <- c(1, l[l > 1 & l < len], len)
        
        # calculating the size of whole slopes
        Ns <- sapply(seq_len(length(lList) - 1), function(i) {
            sum(mList[lList[i]:lList[i + 1]])
        })
        Ns <- Ns[Ns > 0]
        
        # generating function for whole slopes
        genfunc <- do.call("c", lapply(Ns, seq_len))
        
        # generating function for all elements perhaps alowing non
        # complete time series
        for (m in mList) {
            genfunc <- c(genfunc, -seq_len(m))
        }
        
        # generating function for inflection points (have to be counted
        # twice)
        genfunc <- c(genfunc, do.call("c", lapply(l[l > 1 & l < len], 
            function(i) { 
                -seq_len(mList[i])
            })))
        
        # calculate maximum Value of test
        maxval <- sum(sapply(1:(length(lList) - 1), function(i) {
            (sum(mList[lList[i]:lList[i + 1]])^2 - 
                sum(mList[lList[i]:lList[i + 1]]^2)) / 2
        }))
        
        # second step for the cyclic case treatment genetrating function
        # gets the man-whitney test for the special element whith the
        # first slope exept the next inflection maxval is extendet by the
        # maximum possible counts for this test
        if (special != 0 && cycl) {
            addpos <- 1:(lList[2] - 1)
            addpos <- addpos[addpos > 0]
            remain <- sum(mList[addpos])
            genfunc <- c(genfunc, c(-seq_len(special)), c(seq_len(special)
                + remain))
            maxval <- maxval + special * remain
        }
        
    }
    
    # return for the 'intestable'
    if (maxval == 0) 
        return(list(pval = c(1), den = c(0)))
    
    ## as Distribution is symetric only the first half has to be
    ## calculated
    arr <- as.bigz(matrix(c(1, rep(0, ceiling(maxval / 2) - 1)), nrow = 1))
    len <- length(arr)
    
    # use the generating function
    for (gen in genfunc) {
        arr <- foldarr(arr, gen, len)
    }
    
    # combine to a full distribution, calculate density
    if (maxval %% 2 == 1) {
        arr <- cbind(arr, arr[, (ncol(arr) - 1):1])
    }
    if (maxval %% 2 == 0) {
        arr <- cbind(arr, arr[, ncol(arr):1])
    }
    den <- arr/sum(arr)
    
    # return
    return(list(pval = as.double((rev(cumsum(den)))), den = as.double(den)))
} 