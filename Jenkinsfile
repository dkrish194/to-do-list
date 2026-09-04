pipeline{
    agent{
        node{
            label   '186.3'
        }
    }
    environment {
        GITOPS_REPO   = 'https://github.com/dkrish194/to-do-list-k8-helm.git'
        GITOPS_BRANCH = 'main'
        HELM_VALUES   = 'helm-be/values.yaml'   // path inside gitops repo
        IMAGE_TAG     = "${env.BUILD_NUMBER}-${env.GIT_COMMIT?.take(7)}"
    }
    stages{

        stage("READ FRONTEND VERSION"){
            steps{
                script{
                    dir('frontend'){
                        def fe_app_version = sh (script: 'cut -d "=" -f 2  setup-frontend.cfg',returnStdout: true).trim()
                        echo "Extraced frontend appverion value: ${fe_app_version}"
                        env.FE_APP_VERSION=fe_app_version
                    }
                    
                }
            }
        }
        stage("READ BACKEND VERSION"){
            steps{
                script{
                    def be_app_version = sh (script: 'cut -d "=" -f 2  backend/setup-backend.cfg',returnStdout: true).trim()
                    echo "Extraced backend appverion value: ${be_app_version}"
                    env.BE_APP_VERSION=be_app_version
                }
            }
        }
        stage("BUILD FRONTEND IMAGE"){
            steps{
                echo "Building frontend Image"
                sh "docker build -t dkrish194/todo-frontend:${env.FE_APP_VERSION} frontend"
            }
        }
        stage("BUILD BACKEND IMAGE"){
            steps{
                echo "Buildig Backend Image"
                sh "docker build -t dkrish194/todo-backend:${env.BE_APP_VERSION} backend"
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

        stage("DOCKER PUSH FRONTEND"){
            steps{
                 echo "Docker Push Frontend"
            withCredentials([usernamePassword(credentialsId: 'dockerhub-tocken',usernameVariable: 'DOCKER_USER',
                                passwordVariable: 'DOCKER_PASS')]){
                                        sh "docker push dkrish194/todo-frontend:${env.FE_APP_VERSION}"
                                }
            }
           
        }
        stage("DOCKER PUSH BACKEND"){
            steps{
                 echo "Docker Push Backend"
                 withCredentials([usernamePassword(credentialsId: 'dockerhub-tocken',usernameVariable: 'DOCKER_USER',
                                passwordVariable: 'DOCKER_PASS')]){
                                        sh "docker push dkrish194/todo-backend:${env.BE_APP_VERSION}"
                                }
            }
           
        }
        stage('CLONE GIT-OPS REPO'){
            steps{
                script{
                    dir('gitops') {
                        withCredentials([usernamePassword(
                            credentialsId: 'dockerhub-tocken',
                            usernameVariable: 'GIT_USER',
                            passwordVariable: 'GIT_TOKEN'
                        )]) {
                            sh '''
                                git clone --depth 1 --single-branch \
                                    --branch ${GITOPS_BRANCH} \
                                    https://github.com/dkrish194/to-do-list-k8-helm.git .
                            '''
                        }
                } 
                }
            }
        }
        stage('Update BE image tag with yq'){
            steps{
                sh """
                    yq eval '.image.tag = "${env.BE_APP_VERSION}"' -i ${WORKSPACE}/gitops/helm-be/values.yaml
                """
            }
        }
        stage('Update EE image tag with yq'){
            steps{
                sh """
                    yq eval '.image.tag = "${env.FE_APP_VERSION}"' -i ${WORKSPACE}/gitops/helm-fe/values.yaml
                """
            }
        }

        stage('Commit and Push') {
            steps {
                dir('gitops') {
                    withCredentials([usernamePassword(
                        credentialsId: 'dockerhub-tocken',
                        usernameVariable: 'GIT_USER',
                        passwordVariable: 'GIT_TOKEN'
                    )]) {
                        sh '''
                            git config user.email "dkrish194@github.com"
                            git config user.name "dkrish194"
                            git add helm-be/values.yaml
                            git add helm-fe/values.yaml

                            git commit -m "chore: bump image tag to ${IMAGE_TAG} [skip ci]"

                            // # retry with rebase in case another pipeline pushed in the meantime
                             for i in 1 2 3; do
                                git pull --rebase origin ${GITOPS_BRANCH} && \
                                git push https://${GIT_USER}:${GIT_TOKEN}@github.com/dkrish194/to-do-list-k8-helm.git HEAD:${GITOPS_BRANCH} && break
                                sleep 3
                             done

                            
                        '''
                    }
                }
            }
        }
        
      
    }

    post {
        success {
            slackSend(
                channel: '#channel-jenkins',
                color: 'good',
                message: "✅ SUCCESS: ${env.JOB_NAME} #${env.BUILD_NUMBER}\n${env.BUILD_URL}"
            )
        }
        failure {
            slackSend(
                channel: '#channel-jenkins',
                color: 'danger',
                message: "❌ FAILURE: ${env.JOB_NAME} #${env.BUILD_NUMBER}\n${env.BUILD_URL}"
            )
        }
        always{
   
            echo 'inside post always section'
            cleanWs()
        }
}
}