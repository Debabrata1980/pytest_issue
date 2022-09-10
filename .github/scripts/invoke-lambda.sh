#!/bin/bash

if [ $# -lt 2 ]; then
  echo "usage: $(basename "$0") <function-name> <payload-file> [invocation-type] [region]"
  exit 1
fi

function_name=$1
payload_file=$2
invocation_type=$3
region=$4

if [ "${invocation_type}" == "" ]; then
  invocation_type="RequestResponse"
fi
if [ "${region}" == "" ]; then
  region="us-west-2"
fi

# Perform input validation, only "RequestResponse" and "Event" are valid invocation types.
if [[ "${invocation_type}" != "RequestResponse" && "${invocation_type}" != "Event" ]]; then
  echo "Invalid invocation type: ${invocation_type}, only RequestResponse or Event are supported."
  exit 1
fi

# If we're calling the function asynchronously, set the log type to None
log_type="Tail"
if [ "${invocation_type}" == "Event" ]; then
    log_type="None"
fi

# Invoke the Lambda function with the specified input values
echo -e "\nInvoking Lambda ${function_name} in region ${region} with invocation_type=${invocation_type}, log_type=${log_type} and a payload of:"
cat ${payload_file}
sh -c "aws lambda invoke \
    --region ${region} \
    --function-name ${function_name} \
    --invocation-type ${invocation_type} \
    --log-type ${log_type} \
    --payload file://${payload_file} \
    response.json"
echo -e "\nLambda response"
cat response.json

# Check for errors
grep FunctionError response.json &>/dev/null
if [ $? -eq 0 ]; then
  echo -e "\nError invoking Lambda function ${function_name}"
  echo 1
fi
exit 0
