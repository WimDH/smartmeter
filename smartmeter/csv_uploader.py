from typing import List
import argparse
import sys
import glob
import os
import minio


def parse_cli(cli_args: List) -> argparse.Namespace:
    """Process the CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Read and process data from the digital enery meter."
    )
    parser.add_argument(
        "-d",
        "--directory",
        dest="source_dir",
        help="The directory where we look for files.",
    )
    parser.add_argument(
        "-p",
        "--pattern",
        dest="file_pattern",
        help="The file pattern for filtering files.",
    )
    parser.add_argument(
        "-b",
        "--bucket",
        dest="bucket",
        help="Name of the S3 bucket where to upload the files.",
    )
    parser.add_argument("-H", "--hostname", dest="hostname", help="Bucket endpoint.")
    parser.add_argument(
        "-v", dest="verbosity_level", action="count", default=0, help="Verbosity level."
    )

    return parser.parse_args(cli_args)

def copy_file_to_bucket(file: str, endpoint: str, access_key: str, secret_key: str, bucket_name: str) -> None:
    """Copy the file to the bucket."""
    print("Copy file %s", file)

    _, filename = os.path.split(file)
    mc = minio.Minio(endpoint, access_key, secret_key, secure=True)

    try:
        mc.fput_object(bucket_name, filename, file)
        print("Copy done.")
        os.unlink(file)
        print("Deleted local file.")

    except minio.S3Error as err:
        print("Could not copy %s: %s", filename, err)


def main() -> None:
    """Entrypoint"""
    args = parse_cli(sys.argv[1:])
    access_key = os.environ.get("SMARTMETER_ACCESS_KEY")
    secret_key = os.environ.get("SMARTMETER_SECRET_KEY")

    if not access_key or not secret_key:
        print(
            "Set the environment variables SMARTMETER_ACCESS_KEY and SMARTMETER_SECRET_KEY!"
        )
        sys.exit(1)

    files = glob.glob(os.path.join(args.source_dir, args.file_pattern))

    for file in files:
        print("Copying file %s", file)
        copy_file_to_bucket(file, args.hostname, access_key, secret_key, args.bucket)

    sys.stdout.flush()


if __name__ == "__main__":
    main()
