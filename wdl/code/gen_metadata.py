import os
import hashlib
import fnmatch
import json
import pandas as pd
from datetime import datetime
from pymongo import MongoClient
import csv
import json
import fastjsonschema
import copy


class GenMetadata:
    """
    Generate metadata for the pipeline!
    """
    def __init__(self):

        self.dataset_id = None
        self.genome_directory = None
        self.annotation_file_name = None
        self.resultant_file = None
        self.fasta_file = None
        self.contaminant_file = None
        self.peptide_report = None
        self.protein_report = None
        self.qc_metric_report = None
        self.started_at_time = None
        self.ended_at_time = None

        self.activity = {}
        self.data_object = {}
        self.uri = os.environ.get("MONGO_URI")
        self.activity_coll = None
        self.data_obj_coll = None
        self.new = []
        self.quant_bucket = []

    def validate_json(self, json_data):
        try:
            json.loads(json_data)
        except ValueError as err:
            return False
        return True

    def validate_metadata_schema(self, flag, json_data):
        if flag == "activity":
            try:
                self.activity_schema_validator(json_data)
            except fastjsonschema.JsonSchemaException as err:
                return False
            return True
        if flag == "dataobject":
            try:
                self.data_object_schema_validator(json_data)
            except fastjsonschema.JsonSchemaException as err:
                return False
            return True

    def register_job_in_emsl_to_jgi(self, job_key, job_value, emsl_to_jgi_copy):

        locations = emsl_to_jgi_copy[self.dataset_id]["genome_directory"][
            self.genome_directory
        ]
        if job_key not in locations:
            locations[job_key] = job_value
        else:
            print(f"{job_key} already present in {self.genome_directory}")

    def write_to_json_file(self, filenames):
        """

        :param filenames:
        :return:
        """
        activity_count = self.activity_coll.count_documents({})
        data_obj_count = self.data_obj_coll.count_documents({})
        print(f" activity_coll#:{activity_count}, data_obj_coll#:{data_obj_count}")
        with open(filenames[0], "w") as fptr1, open(filenames[1], "w") as fptr2:

            fptr1.write("[\n")
            for idx, activity_doc in enumerate(self.activity_coll.find()):
                activity_doc.pop("_id")
                fptr1.write(json.dumps(activity_doc, default=str, indent=4))
                if idx < activity_count - 1:
                    fptr1.write(",\n")
            fptr1.write("\n]")

            fptr2.write("[\n")
            for idx, do_doc in enumerate(self.data_obj_coll.find()):
                do_doc.pop("_id")
                fptr2.write(json.dumps(do_doc, default=str, indent=4))
                if idx < data_obj_count - 1:
                    fptr2.write(",\n")
            fptr2.write("\n]")

    def make_connection(self, db_name, coll_names):
        """
        1. Make connection to mongodb database
        2. Make cursors available.

        :param db_name: database name
        :param coll_names: list of collection names: _activity then _data_obj
        :return:
        """
        client = MongoClient(self.uri)
        # makes db.coll if not exists.
        self.activity_coll = client[db_name][coll_names[0]]
        self.data_obj_coll = client[db_name][coll_names[1]]

    def get_md5(self, file):
        """
        generates MD5 checksum of a file.

        :param file: filename with absolute path.
        :return: chechsum or empty string.
        """
        if not file in (None, ""):
            md5 = hashlib.md5(open(file, "rb").read()).hexdigest()
            return md5
        else:
            return ""

    def gen_id(self, nersc_seq_id):
        """
        - Generate unique ID foreach dataset in the _activity.json
        """
        txt = "{}\n{}\n{}\n".format(
            str(self.dataset_id),
            str(self.genome_directory),
            str(nersc_seq_id),
            str(self.started_at_time),
            str(self.ended_at_time),
        )
        return "nmdc:{}".format(hashlib.md5(txt.encode("utf-8")).hexdigest())

    def prepare_ProteinQuantification(self):
        with open(self.protein_report, encoding="utf-8-sig") as tsvfile:
            tsvreader = csv.reader(tsvfile, delimiter="\t")
            header = next(tsvreader)
            BestProtein = header[3]
            for line in tsvreader:
                quant_dict = {}
                quant_dict["peptide_sequence_count"] = line[2]
                quant_dict["best_protein"] = "nmdc:" + line[3].replace(" ", "")
                quant_dict["all_proteins"] = [
                    "nmdc:" + protein.replace(" ", "")
                    for protein in line[10].split(",")
                ]
                quant_dict["protein_spectral_count"] = line[13]
                quant_dict["protein_sum_masic_abundance"] = line[14]
                self.quant_bucket.append(quant_dict)

    def prepare_PeptideQuantification(self):
        # print('>>',self.peptide_report)
        with open(self.peptide_report, encoding="utf-8-sig") as tsvfile:
            tsvreader = csv.reader(tsvfile, delimiter="\t")
            header = next(tsvreader)
            for line in tsvreader:
                quant_dict = {}
                quant_dict["peptide_sequence"] = line[2]
                quant_dict["best_protein"] = "nmdc:" + line[3].replace(" ", "")
                quant_dict["all_proteins"] = [
                    "nmdc:" + protein.replace(" ", "")
                    for protein in line[10].split(",")
                ]
                quant_dict["min_q_value"] = line[12]
                quant_dict["peptide_spectral_count"] = line[13]
                quant_dict["peptide_sum_masic_abundance"] = line[14]
                self.quant_bucket.append(quant_dict)
        pass

    def prepare_file_data_object_(self, file_path, file_name, description):
        """
        - Makes entry in _emsl_analysis_data_objects.json
        - Contains information about Pipeline's analysis results E.g.
            1. resultant.tsv
            2. data_out_table.tsv
        """
        checksum = self.get_md5(file_path)
        if checksum:
            file_id = "nmdc:" + checksum
            # print("{} : {}".format(checksum, os.path.basename(file_name) ) )

            self.data_object["id"] = file_id
            self.data_object["name"] = file_name
            self.data_object["description"] = description
            self.data_object["file_size_bytes"] = os.stat(file_path).st_size
            self.data_object["type"] = os.environ.get("TYPE")
            self.data_object["url"] = (
                "https://nmdcdemo.emsl.pnnl.gov/proteomics/" + file_name
            )
            if self.data_obj_coll.count_documents({"id": file_id}, limit=1) == 0:
                self.data_obj_coll.insert_one(self.data_object)
                self.data_object.clear()
            else:
                print("data object already present.")
            # return file_id
        else:
            print("Found HASH empty for {}".format(file_name))

    def create_has_output(self):
        """
        Files:
            MSGFjobs_MASIC_resultant.tsv
            Peptide_Report.tsv
            Protein_Report.tsv
            QC_Metrics.tsv
        Quantification:
            peptide
            #TODO: protein if needed
        """
        has_output = []
        has_output.append(
            self.prepare_file_data_object_(
                self.resultant_file,
                os.path.basename(self.resultant_file),
                "Aggregation of analysis tools{MSGFplus, MASIC} results",
            )
        )
        has_output.append(
            self.prepare_file_data_object_(
                self.peptide_report,
                os.path.basename(self.peptide_report),
                "Aggregated peptides sequences from MSGF+ search results filtered to ~5% FDR",
            )
        )
        has_output.append(
            self.prepare_file_data_object_(
                self.protein_report,
                os.path.basename(self.protein_report),
                "Aggregated protein lists from MSGF+ search results filtered to ~5% FDR",
            )
        )
        has_output.append(
            self.prepare_file_data_object_(
                self.qc_metric_report,
                os.path.basename(self.qc_metric_report),
                "Overall statistics from MSGF+ search results filtered to ~5% FDR",
            )
        )
        self.activity["has_output"] = has_output
        pass

    def create_has_input(self, emsl_to_jgi_copy):
        """
        "has_input":
              - created for .RAW file pointer to Bill's JSON
              - fasta_checksum
              - contaminant_checksum
        """

        emsl_to_jgi = {}
        has_input = []
        # add .RAW
        ptr_to_raw_in_bills_json = "emsl:output_" + self.dataset_id
        has_input.append(ptr_to_raw_in_bills_json)
        # add JGI fasta
        emsl_to_jgi[self.dataset_id] = self.fasta_file
        self.new.append(emsl_to_jgi)
        emsl_to_jgi.clear()
        fasta_checksum = self.get_md5(self.fasta_file)
        if fasta_checksum:
            # print("{} : {}".format(fasta_checksum, self.fasta_file))
            # add to metadata.
            self.register_job_in_emsl_to_jgi(
                "faa_file_checksum", fasta_checksum, emsl_to_jgi_copy
            )
            has_input.append("nmdc:" + fasta_checksum)
            self.activity["has_input"] = has_input
        else:
            print("Found HASH empty for {}".format(self.fasta_file))
        # add EMSL contaminants
        contaminant_checksum = self.get_md5(self.contaminant_file)
        if contaminant_checksum:
            # print("{} : {}".format(contaminant_checksum, self.contaminant_file))
            has_input.append("nmdc:" + contaminant_checksum)
            self.activity["has_input"] = has_input
        else:
            print("Found HASH empty for {}".format(self.fasta_file))

        # add Quantifications
        self.prepare_PeptideQuantification()
        self.activity["has_peptide_quantifications"] = self.quant_bucket
        pass

    def prepare_activity(self, nersc_seq_id, emsl_to_jgi_copy):
        """
        - Makes entry in _MetaProteomicAnalysis_activity.json
        - Foreach dataset, a pointer:
            from : _MetaProteomicAnalysis_activity.json.has_output.[*_file_id]
            to   : _emsl_analysis_data_objects.json."id"

        """

        activity_id = self.gen_id(nersc_seq_id)
        self.activity["id"] = activity_id
        self.activity["name"] = ":".join(
            ["Metaproteome", self.dataset_id, self.genome_directory]
        )
        self.activity["was_informed_by"] = ":".join(["emsl", self.dataset_id])
        self.activity["started_at_time"] = self.started_at_time
        self.activity["ended_at_time"] = self.ended_at_time
        self.activity["type"] = os.environ.get("PIPELINE_TYPE")
        self.activity["execution_resource"] = os.environ.get("EXECUTION_RESOURCE")
        self.activity["git_url"] = os.environ.get("GIT_URL")

        self.create_has_input(emsl_to_jgi_copy)
        self.create_has_output()

        # add to database!
        if self.activity_coll.count_documents({"id": activity_id}, limit=1) == 0:
            self.activity_coll.insert_one(self.activity)
            self.activity.clear()
        else:
            print("data object already present.")
        pass

    def set_keys(
        self,
        dataset_id,
        genome_directory,
        annotation_file_name,
        resultant_file,
        fasta_file,
        contaminant_file,
        peptide_report,
        protein_report,
        qc_metric_report,
        started_at_time,
        ended_at_time,
    ):
        self.dataset_id = dataset_id
        self.genome_directory = genome_directory
        self.annotation_file_name = annotation_file_name
        self.resultant_file = resultant_file
        self.fasta_file = fasta_file
        self.contaminant_file = contaminant_file
        self.peptide_report = peptide_report
        self.protein_report = protein_report
        self.qc_metric_report = qc_metric_report
        self.started_at_time = started_at_time
        self.ended_at_time = ended_at_time


if __name__ == "__main__":

    meta_file = GenMetadata()
    # setup the cursors
    coll_names = [
        f"{os.environ.get('STUDY')}_MetaProteomicAnalysis_activity",
        f"{os.environ.get('STUDY')}_emsl_analysis_data_objects",
    ]
    meta_file.make_connection(os.environ.get("MONGO_INITDB_DATABASE"), coll_names)

    # 1. Make collection and populate them.
    with open(mapper_file, "r+") as json_file:
        emsl_to_jgi = json.load(json_file)
        emsl_to_jgi_copy = copy.deepcopy(emsl_to_jgi)
        contaminant_file = emsl_to_jgi["contaminant_file_loc"]
        # run for each dataset
        for dataset_id, values in emsl_to_jgi.items():
            if dataset_id not in [
                "contaminant_file_loc",
                "analysis_activity_file_loc",
                "data_objects_file_loc",
                "STUDY",
                "tools_used",
            ]:
                # dataset search against a fasta file
                for genome_directory, locations in values["genome_directory"].items():
                    print(f"Prepare activity {dataset_id} : {genome_directory}")
                    meta_file.set_keys(
                        dataset_id,
                        genome_directory,
                        os.path.basename(locations["txt_faa_file_loc"]),
                        locations["resultant_file_loc"],
                        locations["faa_file_loc"],
                        contaminant_file,
                        locations["peptide_report_loc"],
                        locations["protein_report_loc"],
                        locations["qc_metric_report_loc"],
                        locations["started_at_time"],
                        locations["ended_at_time"],
                    )

                    nersc_seq_id = locations["nersc_seq_id"]
                    meta_file.prepare_activity(nersc_seq_id, emsl_to_jgi_copy)

                    # 2. dump collections in json files
                    activity_file = os.path.join(
                        result_loc,
                        f"{os.environ.get('STUDY')}_MetaProteomicAnalysis_activity.json",
                    )
                    data_obj_file = os.path.join(
                        result_loc,
                        f"{os.environ.get('STUDY')}_emsl_analysis_data_objects.json",
                    )
                    meta_file.write_to_json_file([activity_file, data_obj_file])
                    # add meta-data information.
                    emsl_to_jgi_copy["analysis_activity_file_loc"] = activity_file
                    emsl_to_jgi_copy["data_objects_file_loc"] = data_obj_file
                    emsl_to_jgi_copy["contaminant_file_checksum"] = meta_file.get_md5(
                        contaminant_file
                    )

        json_file.seek(0)  # move back to BOF.
        json_file.truncate()
        json_file.write(json.dumps(emsl_to_jgi_copy, default=str, indent=4))
    pass
