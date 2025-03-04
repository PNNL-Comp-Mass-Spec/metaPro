version 1.0

task masic {
    input{
        File   raw_file
        File   masic_param
        String dataset_name
    }
    command {
        mono /app/masic/MASIC_Console.exe \
        /I:~{raw_file} \
        /O:~{'.'} \
        /P:~{masic_param}
    }
    output {
        File   outfile = "${dataset_name}_SICstats.txt"
    }
    runtime {
        docker: 'microbiomedata/metapro-masic:v3.2.7762'
    }
}
task msconvert {
    input{
        File   raw_file
        String dataset_name
    }
    command {
        wine msconvert \
        ~{raw_file} \
        --zlib \
        --filter 'peakPicking true 2-'
    }
    output {
        File   outfile = "${dataset_name}.mzML"
    }
    runtime {
        docker: 'microbiomedata/metapro-msconvert:latest'
    }
}
task msgfplus {
    input{
        File   mzml_file
        File   contaminated_fasta_file
        File   msgfplus_params
        String dataset_name
        String annotation_name
    }
    command {
        java -Xmx32G -jar /app/msgf/MSGFPlus.jar \
        -s ~{mzml_file} \
        -d ~{contaminated_fasta_file} \
        -o "~{dataset_name}.mzid" \
        -conf ~{msgfplus_params} \
        -thread 16 \
        -verbose 1
        echo '>>> moving revCat.fasta file in execution folder.'
        rev_cat_fasta_loc=$(find .. -type f -regex ".*~{annotation_name}_proteins.revCat.fasta")
        cp $rev_cat_fasta_loc ../execution/
    }
    output {
        File   outfile       = "${dataset_name}.mzid"
        File   rev_cat_fasta = "${annotation_name}_proteins.revCat.fasta"
    }
    runtime {
        docker: 'microbiomedata/metapro-msgfplus:v2021.03.22'
    }
}
task mzidtotsvconverter{
    input{
        File   mzid_file
        String dataset_name
    }
    command {
        mono /app/mzid2tsv/net462/MzidToTsvConverter.exe \
        -mzid:~{mzid_file} \
        -tsv:"~{dataset_name}.tsv" \
        -unroll \
        -showDecoy
        echo '>>> moving tsv file in execution folder.'
        tsv_file_loc=$(find .. -type f -regex ".*~{dataset_name}.tsv")
        cp $tsv_file_loc ../execution/
    }
    output {
        File   outfile = "${dataset_name}.tsv"
    }
    runtime {
        docker: 'microbiomedata/metapro-mzidtotsvconverter:v1.4.6'
    }
}
task peptidehitresultsprocrunner {
    input{
        File   tsv_file
#        File   msgfplus_modef_params
#        File   mass_correction_params
        File   msgfplus_params
        File   revcatfasta_file
        String dataset_name
    }
#        -M:~{msgfplus_modef_params} \
#        -T:~{mass_correction_params} \
    command {
        mono /app/phrp/PeptideHitResultsProcRunner.exe \
        -I:~{tsv_file} \
        -N:~{msgfplus_params} \
        -SynPvalue:0.2 \
        -SynProb:0.05 \
        -ProteinMods \
        -F:~{revcatfasta_file} \
        -O:~{'.'}
    }
    output {
        File   outfile = "${dataset_name}_syn.txt"
    }
    runtime {
        docker: 'microbiomedata/metapro-peptidehitresultsprocrunner:v3.0.7842'
    }
}
task masicresultmerge {
    input{
        File   sic_stats_file
        File   synopsis_file
        String dataset_name
    }
    command {
        synopsis_file_loc=$(find .. -type f -regex ".*~{dataset_name}_syn.txt")
        cp $synopsis_file_loc ../execution/
        sic_stats_file_loc=$(find .. -type f -regex ".*~{dataset_name}_SICstats.txt")
        cp $sic_stats_file_loc ../execution/
        mv ~{dataset_name}_syn.txt ~{dataset_name}_msgfplus_syn.txt
        mv ~{dataset_name}_SICstats.txt ~{dataset_name}_SICStats.txt

        mono /app/MASICResultsMerge/MASICResultsMerger.exe \
        ~{dataset_name}_msgfplus_syn.txt
    }
    output {
        File   outfile = "${dataset_name}_msgfplus_syn_PlusSICStats.txt"
    }
    runtime {
        docker: 'microbiomedata/metapro-masicresultsmerge:v2.0.7800'
    }
}

workflow job_analysis{
    input{
        String dataset_name
        String annotation_name
        File   raw_file_loc
        File   faa_file_loc
        String QVALUE_THRESHOLD
        File   MASIC_PARAM_FILENAME
        File   MSGFPLUS_PARAM_FILENAME
        File   CONTAMINANT_FILENAME
    }

    call masic {
        input:
            raw_file    = raw_file_loc,
            masic_param = MASIC_PARAM_FILENAME,
            dataset_name= dataset_name
    }
    call msconvert {
        input:
            raw_file     = raw_file_loc,
            dataset_name = dataset_name
    }
    call msgfplus {
        input:
            mzml_file               = msconvert.outfile,
            contaminated_fasta_file = faa_file_loc,
            msgfplus_params         = MSGFPLUS_PARAM_FILENAME,
            dataset_name            = dataset_name,
            annotation_name         = annotation_name
    }
    call mzidtotsvconverter {
        input:
            mzid_file    = msgfplus.outfile,
            dataset_name = dataset_name
    }
    call peptidehitresultsprocrunner {
        input:
            tsv_file               = mzidtotsvconverter.outfile,
#            msgfplus_modef_params  = "",
#            mass_correction_params = "",
            msgfplus_params        = MSGFPLUS_PARAM_FILENAME,
            revcatfasta_file       = msgfplus.rev_cat_fasta,
            dataset_name           = dataset_name
    }
    call masicresultmerge {
        input:
            sic_stats_file = masic.outfile,
            synopsis_file  = peptidehitresultsprocrunner.outfile,
            dataset_name   = dataset_name
    }

    output {
        File   resultant_file = masicresultmerge.outfile
        String start_time= ""
        String end_time=""
     }

}
