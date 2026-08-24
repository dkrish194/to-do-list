pipeline{
    agent{
        node{
            label   '186.3'
        }
    }
    stages{

        stage("READ VERSION"){
            steps{
                script{
                    def app_version = sh (script: 'cut -d "=" -f 2  setup.cfg',returnStdout: true).trim()
                    echo "Extraced appverion value: ${app_version}"
                    env.APP_VERSION=app_version
                }
               
            }
        }
        stage("BUILD IMAGE"){
            steps{
                echo "Buildig Image"
                // sh "docker build -t dkrish194/to-do-lis-"
            }
        }
      
    }
}
