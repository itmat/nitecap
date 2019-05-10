#!/usr/bin/perl

# Written by Gregory R Grant
# University of Pennsylvani, 2010

if(@ARGV<3) {
    die "
Usage: upside.pl <infile> <num permutations> <num replicates>

Where: <infile> is a tab delimited spreadsheet with one row for each timepoint with the
replicates from condition one first followed by the replicates from condition two.
There is no header lines or columns, just data.  There must be the same number of
replicates at each condition/time.

<num permutations> is a positive integer greater than one.

";
}

open(INFILE, $ARGV[0]) or die "\nError: cannot open file '$ARGV[0]' for reading\n\n";
$num_perms = $ARGV[1];
if(!($num_perms =~ /\d+/)) {
    die "\nError: the number of permutations must be a positive integer greater than 1.\n\n";
} elsif($num_perms <= 1) {
    die "\nError: the number of permutations must be a positive integer greater than 1.\n\n";
}

$num_replicates = $ARGV[2];

$t=0;
$ave1 = 0;
$ave2 = 0;
while($line = <INFILE>) {
    chomp($line);
    @a = split(/\t/,$line);
    $avea = 0;
    for($i=0; $i<$num_replicates; $i++) {
	$data[1][$t][$i] = $a[$i];
	if($a[$i] =~ /\S/) {
	    $avea = $avea + $a[$i];
	    $NUMb[$t]++;
	}
    }
    $avea = $avea / $NUMb[$t];
    $ave1 = $ave1 + $avea;
    $avea = 0;
    for($i=$num_replicates; $i<$num_replicates*2; $i++) {
	$data[0][$t][$i-$num_replicates] = $a[$i];
	if($a[$i] =~ /\S/) {
	    $avea = $avea + $a[$i];
	    $NUMa[$t]++;
	}
    }
    $avea = $avea / $NUMa[$t];
    $ave2 = $ave2 + $avea;
    $t++;
}
close(INFILE);
$num_timepoints = $t;
$ave1 = $ave1 / $num_timepoints;
$ave2 = $ave2 / $num_timepoints;

print "ave1 = $ave1\n";
print "ave2 = $ave2\n";
for($time=0; $time<$num_timepoints; $time++) {
    for($i=0; $i<@{$data[0][$time]}; $i++) {
	if($data[0][$time][$i] =~ /\S/) {
	    $data[0][$time][$i] = $data[0][$time][$i] - $ave2;
	}
    }
    for($i=0; $i<@{$data[1][$time]}; $i++) {
	if($data[1][$time][$i] =~ /\S/) {
	    $data[1][$time][$i] = $data[1][$time][$i] - $ave1;
	}
    }
}

for($time=0; $time<$num_timepoints; $time++) {
    $count[$time]=0;
    for($type=0; $type<2; $type++) {
	$count2[$type][$time]=0;
    }
}
for($type=0; $type<2; $type++) {
    for($time=0; $time<$num_timepoints; $time++) {
	for($i=0; $i<@{$data[$type][$time]}; $i++) {
	    if($data[$type][$time][$i] =~ /\S/) {
		$alldata[$time][$count[$time]] = $data[$type][$time][$i];
		$count[$time]++;
		$count2[$type][$time]++;
	    }
	}
    }
}
#for($time=0; $time<$num_timepoints; $time++) {
#    for($i=0; $i<$count[$time]; $i++) {
#	print "alldata[$time][$i] = $alldata[$time][$i]\n";
#    }
#}

$A = &compute_ave_change(\@alldata);
print "All: $A\n";
for($type=0; $type<2; $type++) {
    $A = &compute_ave_change(\@{$data[$type]});
    print "$type: $A\n";
}

$stat_control = &compute_ave_change(\@{$data[0]});
print "stat_control = $stat_control\n";

$num_perms_where_less=1;
for($p=0; $p<$num_perms; $p++) {
    undef @data_temp;
    for($time=0; $time<$num_timepoints; $time++) {
	$N1 = $count[$time];
	$N2 = $count2[0][$time];
	undef %indexes;
	$num = 0;
	while($num < $N2) {
	    $R = int(rand($N1));
	    if(!(defined $indexes{$R})) {
		$indexes{$R}++;
		$data_temp[$time][$num] = $alldata[$time][$R];
		$num++;
	    }
	}
    }
    $A = &compute_ave_change(\@data_temp);
    if($A > $stat_control) {
	$num_perms_where_less++;
    }
}
$pval = $num_perms_where_less / $num_perms;
if($pval > 1) {
    $pval = 1;
}
print "p-value: $pval\n";

sub compute_ave_change() {
    ($data_ref) = @_;
    @DATA = @{$data_ref};
    $N = @DATA;
    for($i=0; $i<@DATA; $i++) {
	$ave[$i] = 0;
	$N = 0;
	for($j=0; $j<@{$DATA[$i]}; $j++) {
	    if($DATA[$i][$j] =~ /\S/) {
		$ave[$i] = $ave[$i] + $DATA[$i][$j];
		$N++;
	    }
	}
	$ave[$i] = $ave[$i] / $N;
    }
    $AVE = 0;
#    for($i=0; $i<@DATA; $i++) {
#	print "ave[$i] = $ave[$i]\n";
#    }
    for($i=0; $i<@DATA-1; $i++) {
	$x = $ave[$i] - $ave[$i+1];
	if($x < 0) {
	    $x = -1 * $x;
	}
#	print "x=$x\n";
	$AVE = $AVE + $x;
    }
    $AVE = $AVE / (@DATA-1);
    return $AVE;
}
