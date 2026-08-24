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
        stage("BUILD BACKEND IMAGE"){
            steps{
                echo "Buildig Backend Image"
                sh "docker build -t dkrish194/to-do-list-backend:${env.APP_VERSION} ."
            }
        }
        stage("BUILD FRONTEND IMAGE"){
            steps{
                echo "Building frontend Image"
                sh "docker build -t dkrish194/to-do-list-frontend:latest ."
            }
        }
        stage("PUSH IMAGE"){
            steps{
                echo "Push frontend Image"
                withCredentials([usernamePassword(credentialsId: 'dockerhub-tocken',usernameVariable: 'DOCKER_USER',
                                passwordVariable: 'DOCKER_PASS')]){
                                        sh 'echo $DOCKER_PASS | docker login -u $DOCKER_USER --password-stdin'
                                }
            }
        }
      
    }
}
