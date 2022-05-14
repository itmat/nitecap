CREDENTIALS_DIRECTORY=$PWD/.devcontainer/credentials

mkdir -p $CREDENTIALS_DIRECTORY

AWS_DIRECTORY=$CREDENTIALS_DIRECTORY/.aws

ln -s $AWS_DIRECTORY ~/.aws

if [ ! -d $AWS_DIRECTORY ]; then
    read -p "AWS Access Key ID: " AWS_ACCESS_KEY_ID
    read -p "AWS Secret Access Key (input will not be echoed): " -s AWS_SECRET_ACCESS_KEY; echo
    read -p "Default region name: " DEFAULT_REGION_NAME

    mkdir $AWS_DIRECTORY
    
    echo "[default]"                                        >  $AWS_DIRECTORY/credentials
    echo "aws_access_key_id=$AWS_ACCESS_KEY_ID"             >> $AWS_DIRECTORY/credentials
    echo "aws_secret_access_key=$AWS_SECRET_ACCESS_KEY"     >> $AWS_DIRECTORY/credentials

    echo "[default]"                                        >  $AWS_DIRECTORY/config
    echo "region=$DEFAULT_REGION_NAME"                      >> $AWS_DIRECTORY/config
    echo "output=json"                                      >> $AWS_DIRECTORY/config
fi

npm install

echo 'export PATH=$PATH:'$PWD'/node_modules/aws-cdk/bin' >> ~/.bashrc
echo 'export PYTHONPATH='$PWD'/src/computation:'$PWD'/src/server' >> ~/.bashrc
