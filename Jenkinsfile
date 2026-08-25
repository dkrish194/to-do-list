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
        stage("DOCKER LOGIN"){
            steps{
                echo "Docker login"
                withCredentials([usernamePassword(credentialsId: 'dockerhub-tocken',usernameVariable: 'DOCKER_USER',
                                passwordVariable: 'DOCKER_PASS')]){
                                        sh 'echo $DOCKER_PASS | docker login -u $DOCKER_USER --password-stdin'
                                }
            }
        }
        stage("DOCKER PUSH BACKEND"){
            echo "Docker Push Backend"
            withCredentials([usernamePassword(credentialsId: 'dockerhub-tocken',usernameVariable: 'DOCKER_USER',
                                passwordVariable: 'DOCKER_PASS')]){
                                        sh 'docker push dkrish194/to-do-list-backend:${env.APP_VERSION}'
                                }
        }
          stage("DOCKER PUSH FRONTEND"){
            echo "Docker Push Frontend"
            withCredentials([usernamePassword(credentialsId: 'dockerhub-tocken',usernameVariable: 'DOCKER_USER',
                                passwordVariable: 'DOCKER_PASS')]){
                                        sh 'docker push dkrish194/to-do-list-frontend:latest'
                                }
        }
      
    }
}
